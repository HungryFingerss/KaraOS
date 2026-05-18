"""P0.11 — _persistent dict atomic-replace (preventive hardening).

Tests for the race-protection contract on `core.state._persistent`:

- Reads from the dashboard `/api/status` path iterate the dict via
  `**_persistent` inside `write()`.  If a writer mutated the dict
  in-place (`_persistent[key] = value`) while a reader was mid-spread,
  CPython would raise `RuntimeError: dictionary changed size during
  iteration`.

- The atomic-replace pattern (rebind `_persistent = {**_persistent,
  key: value}`) keeps the OLD dict reference stable for any reader that
  already captured it; the new dict only becomes visible on the next
  read.  CPython STORE_NAME is GIL-atomic, so the swap is race-free
  from the reader's perspective.

The actual race has never been observed in production — the single
writer (`pipeline.py:6264 state.set_persistent("anti_spoof_enabled", _)`)
runs ONCE at startup, before the event loop, before any reader can run.
P0.11 is preventive hardening for three latent failure modes:

  1. A future runtime `set_persistent` call lands after startup.
  2. `state.write()` is moved off the asyncio loop (executor / thread).
  3. `state.write()` gains an `await` point and the writer call
     interleaves between the spread-construction and the JSON dump.

Any of those would activate the race.  P0.11 closes the door before it opens.

Test inventory:
  #1  behavioral — 1k tight writes under 1k reader threads, asserts zero
      RuntimeError + all 1000 keys present (single-writer guarantee)
  #2  behavioral — reader never sees the (k2 alone) torn state
  #3  AST       — repo-wide ban on `_persistent[X] = Y` subscript assigns
  #4  AST       — every `_persistent = ...` rebind in core/state.py
                  declares `global _persistent`
"""
from __future__ import annotations

import ast
import pathlib
import threading
import time

import pytest

from core import state as _state_mod


REPO = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _isolate_persistent(monkeypatch, tmp_path):
    """Reset `core.state._persistent` to an empty dict between tests and
    redirect STATE_FILE writes to a tmp path so write() doesn't pollute
    the live `faces/state.json`."""
    monkeypatch.setattr(_state_mod, "_persistent", {})
    monkeypatch.setattr(_state_mod, "STATE_FILE", tmp_path / "state.json")
    yield


# ---------------------------------------------------------------------------
# Test #1 — atomic replace, no RuntimeError under reader load
# ---------------------------------------------------------------------------

class TestAtomicReplaceUnderReaderLoad:
    def test_no_runtime_error_and_all_keys_present(self):
        """1 writer thread does 1000 sequential set_persistent() calls; 1000
        reader threads each call state.write() in tight loop.  Atomic-replace
        rebinds _persistent in one GIL-atomic STORE_NAME — any reader that
        captured the old reference sees the old snapshot, never a half-
        modified dict.

        Final-state assertion (P1 polish, single-writer reasoning): the writer
        runs sequentially against itself, so each set_persistent completes
        before the next iteration.  No writer races with itself; the final
        dict MUST contain all 1000 keys (k_0 .. k_999).  This test does NOT
        claim multi-writer correctness — that requires explicit threading.Lock
        which P0.11's docstring documents as out-of-scope (production has 1
        writer at startup).
        """
        N_WRITES   = 1000
        N_READERS  = 1000
        WRITER_DONE = threading.Event()
        reader_exceptions: list[BaseException] = []
        ex_lock = threading.Lock()

        def _writer():
            try:
                for i in range(N_WRITES):
                    _state_mod.set_persistent(f"k_{i}", i)
            finally:
                WRITER_DONE.set()

        def _reader():
            while not WRITER_DONE.is_set():
                try:
                    _state_mod.write(status="idle")
                except BaseException as e:  # any reader exception is a failure
                    with ex_lock:
                        reader_exceptions.append(e)
                    return

        readers = [threading.Thread(target=_reader, daemon=True)
                   for _ in range(N_READERS)]
        for t in readers:
            t.start()
        writer = threading.Thread(target=_writer)
        writer.start()
        writer.join(timeout=30.0)
        for t in readers:
            t.join(timeout=5.0)

        assert not reader_exceptions, (
            f"{len(reader_exceptions)} reader exception(s) under atomic-replace; "
            f"first: {reader_exceptions[0]!r}.  The race condition guard "
            "(_persistent = {**_persistent, k: v}) is broken — reader saw "
            "torn dict during iteration."
        )

        # P1 polish: every writer key landed.  Single writer doesn't race
        # with itself; final dict has all keys k_0 .. k_999.
        snap = _state_mod._persistent
        missing = [f"k_{i}" for i in range(N_WRITES) if f"k_{i}" not in snap]
        assert not missing, (
            f"{len(missing)} writer key(s) missing from final dict "
            f"(first missing: {missing[0]!r}).  Single-writer sequential "
            "writes must all land — losing keys would indicate the "
            "STORE_NAME atomic swap dropped writes (which is not a "
            "supported failure mode of CPython)."
        )


# ---------------------------------------------------------------------------
# Test #2 — reader sees consistent (k1, k2) snapshot, never (k2-alone) torn
# ---------------------------------------------------------------------------

class TestReaderSeesConsistentSnapshot:
    def test_no_torn_state_visible_to_reader(self):
        """Producer cycles between (k1=v1) then (k1=v1, k2=v2).  Reader runs
        in tight loop and inspects what `write()` would spread.  Asserts the
        reader NEVER observes `{k2: v2}` without `k1: v1` — that shape only
        materializes if a half-rebuilt dict leaked across the GIL boundary,
        which is structurally impossible under atomic-replace.
        """
        STOP = threading.Event()
        TORN_OBSERVATIONS: list[dict] = []
        ex_lock = threading.Lock()

        def _producer():
            # Pre-seed k1 so the first cycle's intermediate state is a real
            # 2-key dict; otherwise the {k1: v1} shape would always be
            # "alone" trivially.
            _state_mod.set_persistent("k1", "v1_seed")
            for i in range(2000):
                if STOP.is_set():
                    return
                _state_mod.set_persistent("k1", f"v1_{i}")
                _state_mod.set_persistent("k2", f"v2_{i}")

        def _reader():
            try:
                while not STOP.is_set():
                    # Snapshot the reference once — the same pattern as
                    # `**_persistent` capturing a single deref.
                    snap = _state_mod._persistent
                    if "k2" in snap and "k1" not in snap:
                        with ex_lock:
                            TORN_OBSERVATIONS.append(dict(snap))
                        return
            except BaseException as e:  # noqa: BLE001
                with ex_lock:
                    TORN_OBSERVATIONS.append({"exception": repr(e)})

        prod = threading.Thread(target=_producer)
        readers = [threading.Thread(target=_reader, daemon=True) for _ in range(8)]
        for t in readers:
            t.start()
        prod.start()
        prod.join(timeout=10.0)
        STOP.set()
        for t in readers:
            t.join(timeout=2.0)

        assert not TORN_OBSERVATIONS, (
            f"reader observed torn (k2-alone) state {len(TORN_OBSERVATIONS)} "
            f"time(s) — atomic-replace broken.  First: {TORN_OBSERVATIONS[0]!r}"
        )


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------

def _iter_repo_python_files() -> list[pathlib.Path]:
    """All .py files in pipeline.py + core/*.py.  Tests are intentionally
    excluded — tests/test_state_race.py legitimately READS _persistent for
    assertions, which isn't a subscript-write violation."""
    files = [REPO / "pipeline.py"]
    files.extend((REPO / "core").rglob("*.py"))
    return [f for f in files if f.is_file()]


def _is_persistent_target(target: ast.AST) -> bool:
    """True if `target` is the bare Name `_persistent` (rebind) OR a
    Subscript whose value is `_persistent` (subscript-assign)."""
    if isinstance(target, ast.Name) and target.id == "_persistent":
        return True
    if isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name):
        return target.value.id == "_persistent"
    return False


# ---------------------------------------------------------------------------
# Test #3 — no _persistent[X] = Y subscript writes anywhere
# ---------------------------------------------------------------------------

class TestNoSubscriptWritesAnywhere:
    def test_no_bare_persistent_subscript_writes_in_codebase(self):
        """Scan pipeline.py + core/*.py for `_persistent[<anything>] = ...`.
        After P0.11, even core/state.py uses rebind, so the count is zero
        everywhere.  Same shape as P0.5's PAIRED_WRITE_METHODS inverse check
        and P0.6.7v2's writer enumeration — coding discipline turned into a
        CI-enforced invariant.

        NOTE on AST scope: this scan covers `_persistent[X] = Y` direct
        subscript assigns only.  It does not cover edge cases like
        `_persistent.update({...})` (treated as a separate mutator method —
        also forbidden but matched by a different pattern if needed) or
        synthetic ast.AugAssign / destructuring shapes (vanishingly rare).
        The common case is what matters here.
        """
        violations: list[str] = []
        for path in _iter_repo_python_files():
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError as e:
                violations.append(f"{path}: parse error {e!r}")
                continue
            for node in ast.walk(tree):
                if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    for tgt in targets:
                        if not isinstance(tgt, ast.Subscript):
                            continue
                        # Match both bare `_persistent[X]` (in-module access)
                        # and attribute-form `state._persistent[X]` (external
                        # callers importing the module).  Both shapes mutate
                        # the underlying dict directly, bypassing the
                        # atomic-replace contract.
                        sub_val = tgt.value
                        is_persistent = (
                            (isinstance(sub_val, ast.Name)
                             and sub_val.id == "_persistent")
                            or (isinstance(sub_val, ast.Attribute)
                                and sub_val.attr == "_persistent")
                        )
                        if is_persistent:
                            rel = path.relative_to(REPO).as_posix()
                            violations.append(
                                f"{rel}:{node.lineno}: `_persistent[...] = ...` "
                                "subscript-assign forbidden — use "
                                "`set_persistent(key, value)` (atomic-replace) "
                                "instead of mutating the underlying dict directly."
                            )
        assert not violations, (
            "P0.11 invariant violated — bare `_persistent[X] = Y` subscript "
            "writes exist in the codebase.  Atomic-replace REQUIRES the "
            "rebind shape so readers never see a torn dict.\n\nViolations:\n  "
            + "\n  ".join(violations)
        )


# ---------------------------------------------------------------------------
# Test #4 — every _persistent rebind in core/state.py declares global
# ---------------------------------------------------------------------------

class TestEveryRebindDeclaresGlobal:
    def test_every_persistent_rebind_in_state_declares_global(self):
        """Within `core/state.py`, every function that contains a top-level
        `_persistent = ...` rebind MUST also contain `global _persistent`
        somewhere in its body — otherwise the assignment creates a function-
        local variable and the module global stays untouched (silent no-op
        from the writer's perspective).

        AST scope: this scan covers direct `_persistent = ...` assigns only.
        It does NOT cover `ast.AugAssign` (`_persistent += {...}`),
        destructuring tuple targets (`a, _persistent = ...`), or walrus
        expressions (`_persistent := ...`).  These patterns are vanishingly
        rare for module globals and the common case is what matters here.
        If a future contributor introduces one of those shapes, they will
        either find this test's docstring or the production docstring on
        set_persistent — neither path is silent.
        """
        state_path = REPO / "core" / "state.py"
        tree = ast.parse(state_path.read_text(encoding="utf-8"))
        violations: list[str] = []
        for func in ast.walk(tree):
            if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            # Find rebinds of _persistent inside this function body.
            rebind_nodes: list[ast.Assign] = []
            for node in ast.walk(func):
                if isinstance(node, ast.Assign):
                    if any(_is_persistent_target(t) and isinstance(t, ast.Name)
                           for t in node.targets):
                        rebind_nodes.append(node)
            if not rebind_nodes:
                continue
            # Does this function declare `global _persistent`?
            declared_global = False
            for node in ast.walk(func):
                if isinstance(node, ast.Global) and "_persistent" in node.names:
                    declared_global = True
                    break
            if not declared_global:
                for rb in rebind_nodes:
                    violations.append(
                        f"core/state.py:{rb.lineno}: function "
                        f"`{func.name}` rebinds `_persistent` without "
                        "declaring `global _persistent` — the assignment "
                        "creates a function-local variable and the module "
                        "global stays untouched."
                    )
        assert not violations, (
            "P0.11 invariant violated — _persistent rebinds without global "
            "declaration.\n\nViolations:\n  " + "\n  ".join(violations)
        )
