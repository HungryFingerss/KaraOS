"""P0.R6.Y — ECAPA voice ID migration to ProcessPoolExecutor worker
(11 logical anchors, anchor LOCK 11 per Plan v3 §3 Option (γ) hybrid).

Validates the ``core/heavy_worker.py`` ECAPA section (D1 + D2 — worker
function + subprocess singleton + lazy-init accessor), the ``core/voice.py``
5-function async cascade (D3 part (a) — `embed`, `_diarize_ecapa_valley`,
`_diarize_pyannote`, `diarize`, `identify` all `async def`), the ``embed()``
body migration to ``hw.run_heavy("ecapa_embed", ...)`` (D3 part (b)),
the 5 ``pipeline.py`` caller migrations including the LOAD-BEARING
asyncio-fix at site 7148 (D3 caller migration), and the ``pipeline.py::run()``
startup wiring extension (D4).

Per Plan v3 §3 LOCK: 11 anchors at mid 10 INCLUSIVE ±15% band [8.5, 11.5].

Hybrid surface:
- A1-A2, A8: source-inspection (substring + module-level FunctionDef +
  HealthSnapshot field membership)
- A3-A4, A5, A6, A7, A9: AST positive/inverse/line-order checks on
  ``core/voice.py`` + ``pipeline.py``
- A10 EXTENDED: regex scan across all test files for Shape A/B/C patterns
- A11 NEW: regex lookbehind scan for Shape D direct-call missing-await

Anchor-to-deliberate-regression mapping (per Plan v3 §5 item 3):
- (a) Delete ``ecapa_embed_worker`` from ``core/heavy_worker.py`` → A1
- (b) Replace ``_get_subprocess_ecapa()`` body with unconditional None → A2
- (c) Revert ``embed()`` body to ``_embedder.encode_batch(signal)`` direct
  call → A3 + A4
- (d) Revert any one of the 5 ``async def`` signatures back to ``def`` → A5
- (e) Revert ``pipeline.py:7148`` from ``await voice_mod.identify(...)``
  to sync ``voice_mod.identify(...)`` → A6
- (f) Restore ``run_in_executor(None, voice_mod.embed/identify, ...)``
  wrapper at any of sites 2274/2304/7414 OR
  ``run_in_executor(get_diarize_executor(), voice_mod.diarize, ...)``
  at 7450 → A7
- (g) Drop ``hw.get_or_create_pool("ecapa_embed")`` from
  ``pipeline.py::run()`` startup → A8 + A9
- (h) Inject ``MagicMock`` patch for async voice fn in test file → A10
- (i) Convert 1 of 9 Shape D direct calls back to non-await form → A11
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
# A1 (D1) — ecapa_embed_worker module-level function
# ---------------------------------------------------------------------------


def test_p0_r6_y_d1_anchor_1_ecapa_worker_function_exists() -> None:
    """A1 — ``ecapa_embed_worker`` is defined at MODULE SCOPE in
    ``core/heavy_worker.py`` (NOT nested inside another function).
    Module-level definition is required for pickleability —
    ProcessPoolExecutor's spawn-based IPC pickles the function reference;
    nested functions can't be pickled.

    Per Plan v3 §5 (a) deliberate-regression: deleting the function from
    the module fires this anchor.
    """
    tree = ast.parse(_HEAVY_WORKER.read_text(encoding="utf-8"))
    module_level_funcs = {
        node.name for node in tree.body if isinstance(node, ast.FunctionDef)
    }
    assert "ecapa_embed_worker" in module_level_funcs, (
        f"D1 regression: ecapa_embed_worker must be defined at module "
        f"scope in core/heavy_worker.py (pickleability requirement). "
        f"Current module-level functions: {sorted(module_level_funcs)}."
    )
    import core.heavy_worker as hw  # noqa: PLC0415

    assert callable(getattr(hw, "ecapa_embed_worker", None)), (
        "D1 regression: ecapa_embed_worker not callable after import."
    )


# ---------------------------------------------------------------------------
# A2 (D2) — _SUBPROCESS_ECAPA_EMBEDDER singleton + accessor
# ---------------------------------------------------------------------------


def test_p0_r6_y_d2_anchor_1_subprocess_ecapa_singleton_and_accessor() -> None:
    """A2 — ``_SUBPROCESS_ECAPA_EMBEDDER`` module-level singleton +
    lazy-init accessor ``_get_subprocess_ecapa()`` present in
    ``core/heavy_worker.py``.

    Singleton enforces "model loads ONCE per subprocess lifetime" — the
    persistent-worker invariant from Plan v1 §2.2. Without the accessor,
    every worker call would pay the ~1-2s EncoderClassifier load cost.

    Per Plan v3 §5 (b) deliberate-regression: replacing the accessor body
    with unconditional ``return None`` fires this anchor (lazy-init shape
    check requires both the global declaration AND a construction
    attempt).
    """
    source = _HEAVY_WORKER.read_text(encoding="utf-8")

    assert "_SUBPROCESS_ECAPA_EMBEDDER" in source, (
        "D2 regression: _SUBPROCESS_ECAPA_EMBEDDER module-level singleton "
        "missing from core/heavy_worker.py. Per Plan v1 §2.2, the singleton "
        "is the persistent-worker contract anchor (load-once per "
        "subprocess)."
    )

    tree = ast.parse(source)
    module_level_funcs = {
        node.name for node in tree.body if isinstance(node, ast.FunctionDef)
    }
    assert "_get_subprocess_ecapa" in module_level_funcs, (
        f"D2 regression: _get_subprocess_ecapa() accessor missing. "
        f"Current module-level functions: {sorted(module_level_funcs)}."
    )

    # Lazy-init shape check — accessor body must (a) declare global AND
    # (b) attempt EncoderClassifier construction. Unconditional-None body
    # would pass module-level checks but break the load contract.
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "_get_subprocess_ecapa":
            globals_declared = any(
                isinstance(s, ast.Global)
                and "_SUBPROCESS_ECAPA_EMBEDDER" in s.names
                for s in ast.walk(node)
            )
            assert globals_declared, (
                "D2 regression: _get_subprocess_ecapa() body missing "
                "`global _SUBPROCESS_ECAPA_EMBEDDER` declaration. "
                "Without the global, the lazy-init assignment creates a "
                "function-local instead of populating the module "
                "singleton."
            )
            encoder_calls = [
                n for n in ast.walk(node)
                if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute)
                and n.func.attr == "from_hparams"
            ]
            assert encoder_calls, (
                "D2 regression: _get_subprocess_ecapa() body missing "
                "EncoderClassifier.from_hparams(...) construction. The "
                "lazy-init contract requires constructing the model on "
                "first call; an unconditional `return None` body bypasses "
                "this."
            )
            break


# ---------------------------------------------------------------------------
# A3 (D3 part b) — embed() body dispatches to hw.run_heavy("ecapa_embed", ...)
# ---------------------------------------------------------------------------


def test_p0_r6_y_d3_anchor_1_embed_body_uses_hw_run_heavy() -> None:
    """A3 — ``core/voice.py::embed()`` body contains a positive
    ``hw.run_heavy("ecapa_embed", ...)`` Call node (AST scan, not
    substring — docstring mentions of the task name would pass a substring
    check even after the actual Call was reverted).

    Per Plan v3 §5 (c) deliberate-regression: reverting the body to a
    direct ``_embedder.encode_batch(signal)`` sync call fires this anchor
    (the ``hw.run_heavy`` Call disappears).
    """
    source = _VOICE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    found = False
    for fn_node in tree.body:
        if not (isinstance(fn_node, ast.AsyncFunctionDef) and fn_node.name == "embed"):
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
                and node.args[0].value == "ecapa_embed"
            ):
                found = True
                break
        break

    assert found, (
        "D3 regression (positive check): core/voice.py::embed() body does "
        "not call hw.run_heavy(\"ecapa_embed\", ...). Per Plan v1 §2.3, "
        "the migrated body must offload inference to the heavy-worker "
        "subprocess; reverting to direct _embedder.encode_batch(...) "
        "call would block the asyncio event loop for the duration of "
        "inference."
    )


# ---------------------------------------------------------------------------
# A4 (D3 part b) — embed() body does NOT contain _embedder.encode_batch call
# ---------------------------------------------------------------------------


def test_p0_r6_y_d3_anchor_2_embed_body_no_direct_encode_batch() -> None:
    """A4 — ``core/voice.py::embed()`` body must NOT contain a direct
    ``_embedder.encode_batch(...)`` Call node (inverse check; the worker
    subprocess now owns the inference call).

    Per Plan v3 §5 (c) deliberate-regression: reverting the body to a
    direct ``_embedder.encode_batch(signal)`` call fires this inverse
    anchor. The worker module
    ``core/heavy_worker.py::ecapa_embed_worker`` legitimately calls
    ``embedder.encode_batch(signal)`` (note: local var ``embedder``, not
    ``_embedder``); that's expected and OUT OF SCOPE for this anchor
    (which scans ``core/voice.py`` only).
    """
    source = _VOICE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    direct_encode_calls = []
    for fn_node in tree.body:
        if not (isinstance(fn_node, ast.AsyncFunctionDef) and fn_node.name == "embed"):
            continue
        for node in ast.walk(fn_node):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "_embedder"
                and func.attr == "encode_batch"
            ):
                direct_encode_calls.append(node.lineno)
        break

    assert not direct_encode_calls, (
        f"D3 regression (inverse check): core/voice.py::embed() body "
        f"contains direct _embedder.encode_batch(...) Call nodes at lines "
        f"{direct_encode_calls}. Per Plan v1 §2.3 post-migration, the "
        f"body must NOT do the inference inline; offload via "
        f"hw.run_heavy(\"ecapa_embed\", ...) and let the worker subprocess "
        f"hold the model singleton. Direct sync inference blocks the "
        f"asyncio loop."
    )


# ---------------------------------------------------------------------------
# A5 (D3 part a) — 5 ECAPA-touching functions all async def
# ---------------------------------------------------------------------------


def test_p0_r6_y_d3_anchor_3_five_functions_async_def_cascade() -> None:
    """A5 — all 5 ECAPA-touching functions in ``core/voice.py``
    (``embed``, ``_diarize_ecapa_valley``, ``_diarize_pyannote``,
    ``diarize``, ``identify``) have ``async def`` signatures.

    AST signature-cascade check: all 5 must appear as
    ``ast.AsyncFunctionDef`` nodes at module scope. The cascade is
    load-bearing because internal calls between these functions use
    ``await`` propagation (e.g. ``identify()`` awaits ``embed()``;
    ``_diarize_ecapa_valley()`` awaits both).

    Per Plan v3 §5 (d) deliberate-regression: reverting any one of the 5
    signatures back to ``def`` fires this anchor.
    """
    tree = ast.parse(_VOICE.read_text(encoding="utf-8"))
    REQUIRED_ASYNC = {
        "embed",
        "_diarize_ecapa_valley",
        "_diarize_pyannote",
        "diarize",
        "identify",
    }
    async_defs = {
        node.name for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef)
    }
    sync_defs = {
        node.name for node in tree.body
        if isinstance(node, ast.FunctionDef)
    }
    missing = REQUIRED_ASYNC - async_defs
    sync_violations = REQUIRED_ASYNC & sync_defs
    assert not missing and not sync_violations, (
        f"D3 regression (async signature cascade): all 5 ECAPA-touching "
        f"functions must be `async def`. Missing async defs: "
        f"{sorted(missing) or 'none'}. Functions still `def` (sync): "
        f"{sorted(sync_violations) or 'none'}. Per Plan v1 §2.3 part (a) "
        f"Q1 (a) lock, reverting ANY of the 5 to `def` breaks the await-"
        f"propagation cascade and reintroduces asyncio-blocking inference."
    )


# ---------------------------------------------------------------------------
# A6 (D3 site 7148) — LOAD-BEARING asyncio-fix at pipeline.py:7148
# ---------------------------------------------------------------------------


def test_p0_r6_y_d3_anchor_4_site_7148_uses_await_voice_mod_identify() -> None:
    """A6 — ``pipeline.py:7148`` (voice-first ambient-listen path) uses
    ``await voice_mod.identify(...)`` (positive) AND does NOT contain a
    sync ``voice_mod.identify(...)`` direct call WITHOUT await
    (inverse — LOAD-BEARING asyncio-release fix).

    Site 7148 was the only ECAPA call site that was a SYNC DIRECT CALL
    pre-migration (not wrapped in ``run_in_executor``). Per Plan v1 §1.2,
    this site was the most-impactful asyncio-block — every voice-first
    re-engagement turn blocked the event loop for ~80-150ms during
    ECAPA inference. Migration to ``await voice_mod.identify(...)`` is
    the load-bearing fix.

    Per Plan v3 §5 (e) deliberate-regression: reverting line 7148 from
    ``await voice_mod.identify(...)`` to sync ``voice_mod.identify(...)``
    fires this anchor.
    """
    source = _PIPELINE.read_text(encoding="utf-8")
    tree = ast.parse(source)

    # Positive: count Await(Call(Attribute(voice_mod, identify))) nodes in
    # the full module. Plan v3 expects 5 such caller migrations across
    # 2274/2304/7148/7414/7450; A7 enforces the total count of 5. Here
    # A6 just verifies that site 7148 (LOAD-BEARING) is one of them.
    voice_mod_identify_awaits = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Await):
            continue
        if not isinstance(node.value, ast.Call):
            continue
        func = node.value.func
        if (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "voice_mod"
            and func.attr == "identify"
        ):
            voice_mod_identify_awaits.append(node.lineno)

    # Verify at least one `await voice_mod.identify(...)` lives inside the
    # voice-first ambient-listen scope (the LOAD-BEARING site that was
    # pre-migration a sync direct call). Scope-based detection replaces
    # the brittle ±N line-number tolerance — line numbers shift every
    # cycle as new code lands (P0.R6.Z added pool warm-up + P0.R8 added
    # heavy_worker_watchdog ~80 lines etc.). The scope test asks
    # "is the call inside an `if not _session_store.peek_all_snapshots()`
    # test block?" which uniquely identifies the voice-first ambient-
    # listen path that was site 7148 pre-P0.R6.Y.
    tree = ast.parse(source)
    in_voice_first_scope = False
    for node in ast.walk(tree):
        # Match `if not _session_store.peek_all_snapshots()` test shape.
        if not isinstance(node, ast.If):
            continue
        test = node.test
        # Top-level `not <something>` or `not <a> and <b>` shape.
        unary_not_call = None
        if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
            unary_not_call = test.operand
        elif isinstance(test, ast.BoolOp) and isinstance(test.op, ast.And):
            # `if not X and ...` — check the first operand.
            first = test.values[0]
            if isinstance(first, ast.UnaryOp) and isinstance(first.op, ast.Not):
                unary_not_call = first.operand
        if not (isinstance(unary_not_call, ast.Call)):
            continue
        # Verify the call is _session_store.peek_all_snapshots().
        call_func = unary_not_call.func
        if not (
            isinstance(call_func, ast.Attribute)
            and isinstance(call_func.value, ast.Name)
            and call_func.value.id == "_session_store"
            and call_func.attr == "peek_all_snapshots"
        ):
            continue
        # Inside this If body, look for await voice_mod.identify(...).
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Await):
                continue
            if not isinstance(sub.value, ast.Call):
                continue
            sub_func = sub.value.func
            if (
                isinstance(sub_func, ast.Attribute)
                and isinstance(sub_func.value, ast.Name)
                and sub_func.value.id == "voice_mod"
                and sub_func.attr == "identify"
            ):
                in_voice_first_scope = True
                break
        if in_voice_first_scope:
            break

    assert in_voice_first_scope, (
        f"D3 regression (LOAD-BEARING site 7148 scope-based): no "
        f"`await voice_mod.identify(...)` Call inside the voice-first "
        f"ambient-listen scope (`if not _session_store.peek_all_snapshots() "
        f"and ... == PipelineState.WATCHING:`). Found awaits at: "
        f"{voice_mod_identify_awaits}. Per Plan v1 §1.2, this site was "
        f"the only ECAPA sync DIRECT CALL pre-migration; reverting it "
        f"reintroduces the asyncio-block. Scope-based detection replaces "
        f"the prior line-number tolerance — line shifts across cycles "
        f"(P0.R6.Z + P0.R8) made the tolerance approach brittle."
    )


# ---------------------------------------------------------------------------
# A7 (D3 caller migration) — 5 pipeline.py caller sites; wrapper patterns gone
# ---------------------------------------------------------------------------


def test_p0_r6_y_d3_anchor_5_caller_migration_count() -> None:
    """A7 — 5 ``pipeline.py`` caller sites use direct
    ``await voice_mod.X(...)`` (positive count) AND wrapper patterns
    ``run_in_executor(None, voice_mod.embed/identify, ...)`` +
    ``run_in_executor(get_diarize_executor(), voice_mod.diarize, ...)``
    are GONE (inverse count = 0).

    Per Plan v1 §1.2, 5 production callers migrated:
    - 2274: ``loop.run_in_executor(None, voice_mod.identify, ...)`` → ``await voice_mod.identify(...)``
    - 2304: ``await loop.run_in_executor(None, voice_mod.embed, audio)`` → ``await voice_mod.embed(audio)``
    - 7148 (LOAD-BEARING): sync ``voice_mod.identify(...)`` → ``await voice_mod.identify(...)``
    - 7414: ``loop.run_in_executor(None, voice_mod.identify, ...)`` → ``await voice_mod.identify(...)``
    - 7450: ``_ev_loop.run_in_executor(voice_mod.get_diarize_executor(), voice_mod.diarize, ...)`` → ``await voice_mod.diarize(...)``

    Per Plan v3 §5 (f) deliberate-regression: restoring any of the
    wrapper patterns at any of the 5 sites fires this anchor (the
    inverse-count assertion becomes non-zero).
    """
    source = _PIPELINE.read_text(encoding="utf-8")
    tree = ast.parse(source)

    # Positive: count Await(Call(Attribute(voice_mod, {embed,identify,diarize}))) nodes
    direct_await_calls = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Await):
            continue
        if not isinstance(node.value, ast.Call):
            continue
        func = node.value.func
        if (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "voice_mod"
            and func.attr in ("embed", "identify", "diarize")
        ):
            direct_await_calls += 1

    assert direct_await_calls >= 5, (
        f"D3 regression (positive count): expected at least 5 "
        f"`await voice_mod.{{embed,identify,diarize}}(...)` calls in "
        f"pipeline.py per Plan v1 §1.2 (sites 2274 + 2304 + 7148 + 7414 + "
        f"7450). Found {direct_await_calls}. Reverting any site to the "
        f"`run_in_executor(..., voice_mod.X, ...)` wrapper pattern would "
        f"drop this count below 5."
    )

    # Inverse: no `run_in_executor` Call passing voice_mod.embed/identify/diarize
    # as the function argument (those are the wrapper patterns Plan v3 §5 (f)
    # forbids).
    wrapper_violations = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (
            isinstance(func, ast.Attribute)
            and func.attr == "run_in_executor"
        ):
            continue
        # Second positional arg (after executor) is the callable; check if
        # it's voice_mod.embed/identify/diarize. Signature:
        # `loop.run_in_executor(executor, func, *args)`.
        if len(node.args) < 2:
            continue
        second_arg = node.args[1]
        if (
            isinstance(second_arg, ast.Attribute)
            and isinstance(second_arg.value, ast.Name)
            and second_arg.value.id == "voice_mod"
            and second_arg.attr in ("embed", "identify", "diarize")
        ):
            wrapper_violations.append(node.lineno)

    assert not wrapper_violations, (
        f"D3 regression (inverse check): pipeline.py contains "
        f"`run_in_executor(..., voice_mod.{{embed,identify,diarize}}, ...)` "
        f"wrapper patterns at lines {wrapper_violations}. Per Plan v1 §1.2 "
        f"post-migration, all 5 caller sites must use direct "
        f"`await voice_mod.X(...)` shape. The wrapper pattern was the "
        f"pre-migration shape that blocked the asyncio loop on a thread "
        f"executor."
    )


# ---------------------------------------------------------------------------
# A8 (D4) — HealthSnapshot has ecapa_embed in heavy_worker_status
# ---------------------------------------------------------------------------


def test_p0_r6_y_d4_anchor_1_health_snapshot_includes_ecapa_status() -> None:
    """A8 — ``HealthSnapshot.heavy_worker_status`` dict reports the
    ``"ecapa_embed"`` key after pipeline startup wiring fires.

    Source-inspection: ``pipeline.py::run()`` startup calls
    ``set_heavy_worker_status("ecapa_embed", "healthy")``. Without the
    wiring, the dict would lack the key and operators would see no
    health signal for the ECAPA pool.

    Per Plan v3 §5 (g) deliberate-regression: dropping the
    ``set_heavy_worker_status("ecapa_embed", ...)`` line fires this anchor.
    """
    source = _PIPELINE.read_text(encoding="utf-8")
    assert 'set_heavy_worker_status("ecapa_embed", "healthy")' in source, (
        "D4 regression: pipeline.run() startup missing "
        'set_heavy_worker_status("ecapa_embed", "healthy") call. Per '
        "Plan v1 §2.4, the initial state must mark the pool as healthy in "
        "the observability surface alongside adaface_embed + "
        "whisper_transcribe."
    )


# ---------------------------------------------------------------------------
# A9 (D4) — startup AST line-order: ecapa_embed pool BEFORE vision task spawn
# ---------------------------------------------------------------------------


def test_p0_r6_y_d4_anchor_2_ecapa_pool_spawn_before_vision_task() -> None:
    """A9 — ``pipeline.run()`` startup spawns the ecapa_embed heavy-
    worker pool BEFORE the vision task AND AFTER the AdaFace + Whisper
    pools (D4 ordering invariant; all 3 worker pools must be ready
    before vision task spawn — which can indirectly trigger ECAPA via
    multi-speaker diarize / per-turn voice ID / voice-first ambient-
    listen paths).

    Source-inspection line-order check (same pattern as P0.R6 A7 +
    P0.R6.X A7): locate the
    ``hw.get_or_create_pool("ecapa_embed")`` line + the
    ``_vision_task = asyncio.create_task(_background_vision_loop(...))``
    line + the prior ``hw.get_or_create_pool("whisper_transcribe")`` line,
    assert: whisper < ecapa < vision_task.

    Per Plan v3 §5 (g) deliberate-regression: reversing the order OR
    dropping the warm-up entirely fires this anchor.
    """
    source = _PIPELINE.read_text(encoding="utf-8")
    lines = source.splitlines()

    adaface_pool_line = None
    whisper_pool_line = None
    ecapa_pool_line = None
    vision_task_line = None
    for i, line in enumerate(lines, start=1):
        if adaface_pool_line is None and 'hw.get_or_create_pool("adaface_embed")' in line:
            adaface_pool_line = i
        if whisper_pool_line is None and 'hw.get_or_create_pool("whisper_transcribe")' in line:
            whisper_pool_line = i
        if ecapa_pool_line is None and 'hw.get_or_create_pool("ecapa_embed")' in line:
            ecapa_pool_line = i
        if vision_task_line is None and "_vision_task = asyncio.create_task(" in line:
            vision_task_line = i
        if all(x is not None for x in (
            adaface_pool_line, whisper_pool_line, ecapa_pool_line, vision_task_line
        )):
            break

    assert ecapa_pool_line is not None, (
        "D4 regression: pipeline.run() does not call "
        'hw.get_or_create_pool("ecapa_embed") at startup. Per Plan v1 '
        "§2.4, the ecapa worker pool must be warmed up before the vision "
        "task spawns."
    )
    assert vision_task_line is not None, (
        "D4 sanity: _vision_task = asyncio.create_task(...) not found in "
        "pipeline.py — has the P0.R3 D5 + P0.R6 D5 + P0.R6.X wiring been "
        "removed?"
    )
    assert adaface_pool_line is not None and whisper_pool_line is not None, (
        "D4 sanity: prior pool warm-ups (adaface + whisper) missing — "
        "P0.R6 + P0.R6.X wiring regressed."
    )
    assert adaface_pool_line < whisper_pool_line < ecapa_pool_line < vision_task_line, (
        f"D4 regression (ordering invariant): pool warm-ups out of order. "
        f"Expected: adaface ({adaface_pool_line}) < whisper "
        f"({whisper_pool_line}) < ecapa ({ecapa_pool_line}) < vision "
        f"({vision_task_line}). Per Plan v1 §2.4, all 3 pools MUST be "
        f"ready before vision task spawn so first await voice_mod.X() "
        f"call has a warm subprocess."
    )


# ---------------------------------------------------------------------------
# A10 EXTENDED (PI #1/#2 absorption) — programmatic test-patch enforcement
# ---------------------------------------------------------------------------


def test_p0_r6_y_a10_test_patches_use_asyncmock_for_async_functions() -> None:
    """A10 EXTENDED — programmatic enforcement: all patches/stubs of
    async voice_mod functions (``embed``, ``identify``,
    ``_diarize_ecapa_valley``, ``_diarize_pyannote``, ``diarize``) across
    all test files use ``AsyncMock`` OR ``async def`` wrapper. Catches
    future test additions that drift to ``MagicMock``.

    PI #1 + PI #2 absorption per Plan v3 §1.5 Option (γ) hybrid. Surface:
    29 sites (Shape A/B/C) per Plan v3 §1.3.A-C across 6 test files
    (test_pipeline.py + tests/conftest.py + 4 tests/test_*.py files).

    Per Plan v3 §5 (h) deliberate-regression: injecting a ``MagicMock``
    patch for any of the 5 async voice fns in any test file fires this
    anchor.
    """
    # Scan all test files (including subdirectory)
    test_files = [
        _REPO_ROOT / "test_pipeline.py",
        _REPO_ROOT / "tests" / "conftest.py",
    ]
    # Additionally walk tests/ for any test_*.py files
    for test_file in (_REPO_ROOT / "tests").rglob("test_*.py"):
        if test_file not in test_files:
            test_files.append(test_file)

    ASYNC_VOICE_FNS = ("embed", "identify", "_diarize_ecapa_valley",
                       "_diarize_pyannote", "diarize")

    patterns = [
        # Shape A: patch("module.fn", ...)
        re.compile(
            r'patch\(["\'](?:pipeline\.voice_mod|core\.voice)\.('
            + '|'.join(ASYNC_VOICE_FNS) + r')["\']'
        ),
        # Shape B: patch.object(module, "fn", ...)
        re.compile(
            r'patch\.object\([^,]+,\s*["\'](' + '|'.join(ASYNC_VOICE_FNS) + r')["\']'
        ),
        # Shape C: module-stub-assignment (covers _voice_stub, _vs, _voice_mod aliases)
        re.compile(
            r'(?:_voice_stub|_vs|_voice_mod)\.('
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
                    violations.append(f"{rel_path}:{line_no} — async fn "
                                     f"`{match.group(1)}` mocked with MagicMock; "
                                     f"requires AsyncMock OR async def wrapper")

    assert not violations, (
        f"P0.R6.Y A10 — {len(violations)} test patch sites use MagicMock "
        f"for async ECAPA functions: " + "; ".join(violations)
    )


# ---------------------------------------------------------------------------
# A11 NEW (PI #2 absorption — Shape D) — programmatic direct-call enforcement
# ---------------------------------------------------------------------------


def test_p0_r6_y_a11_test_direct_calls_use_await_for_async_functions() -> None:
    """A11 NEW — programmatic enforcement: all direct calls to async
    voice_mod functions (``embed``, ``identify``, ``_diarize_ecapa_valley``,
    ``_diarize_pyannote``, ``diarize``) in tests must be preceded by
    ``await`` keyword. Catches future test additions that forget async
    migration.

    PI #2 absorption per Plan v3 §1.5 Option (γ) hybrid. Surface: 9 sites
    (Shape D) per Plan v3 §1.3.D in test_pipeline.py.

    Per Plan v3 §5 (i) deliberate-regression: converting 1 of 9 Shape D
    direct calls back to non-await form fires this anchor.
    """
    test_files = [_REPO_ROOT / "test_pipeline.py"]
    # P0.R6.Z extension: exclude the anchor test files themselves —
    # they document the rule in docstrings (regression mapping), not
    # enforce it on themselves. Matches P0.R6.Z A11 _ANCHOR_FILES set.
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

    # Regex: _voice_mod.fn(...) NOT preceded by `await ` keyword.
    # Lookbehind asserts that "await " does NOT precede the call site.
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
            violations.append(f"{rel_path}:{line_no} — direct call to async "
                             f"`_voice_mod.{match.group(1)}(...)` missing "
                             f"`await` keyword; test function must be "
                             f"`async def`")

    assert not violations, (
        f"P0.R6.Y A11 — {len(violations)} direct calls to async ECAPA "
        f"functions missing `await`: " + "; ".join(violations)
    )
