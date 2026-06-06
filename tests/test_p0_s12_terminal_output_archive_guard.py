"""P0.S12 — terminal_output.md PermissionError on multiprocessing.spawn re-import.

P1.A1 SP-4.1 REPOINT: the log harness moved pipeline.py -> runtime/log_capture.py.
The __main__ boot guard stays in pipeline.py but now ATTRIBUTE-REBINDS log_capture's
rebound globals (log_capture._LOG_FILE = ..., etc.) — the only correct shape, since
_log_drain + _check (running in log_capture's namespace) and core.health (reading the
drain counters) all resolve them there. A from-import + bare assignment would snapshot
a pipeline-local and leave _log_drain staring at None.

  A1 — guard contains all 5 Tier-1 log_capture.X signatures (archive, _LOG_FILE open,
       thread start, Tee install, success print), byte-for-byte ORDERING preserved.
  A2 — _LOG_FILE / _archived_log None placeholders live in runtime/log_capture.py now.
  A3 — inline doc block at the guard mentions all anchors (P0.S12, Windows-spawn-mode,
       canary log, 5-bullet, DO-NOT-MOVE, the SP-4.1 attribute-rebind rationale).
  A4 — BEHAVIORAL spawn re-import: subprocess imports pipeline + asserts
       log_capture._LOG_FILE / _archived_log are None (guard did NOT run on import).
  A5 — BEHAVIORAL _log_drain still importable via `from pipeline import _log_drain`
       (re-export survives the move).
  A6 — AST forward-property tripwire (FORALL): EVERY Tier-1 statement (log_capture.X
       attribute shape) lives as a descendant of the `if __name__ == "__main__":` If
       node. Injecting a Tier-1 site OUTSIDE the guard fires this.

Spec: tests/p0_s12_terminal_output_archive_guard_plan_v1.md
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import ast
import multiprocessing
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_PIPELINE_PATH = _REPO_ROOT / "pipeline.py"
_LOG_CAPTURE_PATH = _REPO_ROOT / "runtime" / "log_capture.py"


# ───────────────────────────────────────────────────────────────────────
# Shared helpers
# ───────────────────────────────────────────────────────────────────────


def _load_pipeline_ast() -> ast.Module:
    return ast.parse(_PIPELINE_PATH.read_text(encoding="utf-8"))


def _find_main_guard_if_node(tree: ast.Module) -> ast.If | None:
    """Return the FIRST module-top-level `if __name__ == "__main__":` If node
    (the P0.S12 boot guard — NOT the entry-point block at file end)."""
    for node in tree.body:
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if not isinstance(test, ast.Compare):
            continue
        if not isinstance(test.left, ast.Name) or test.left.id != "__name__":
            continue
        if not (len(test.ops) == 1 and isinstance(test.ops[0], ast.Eq)):
            continue
        if not (len(test.comparators) == 1 and isinstance(test.comparators[0], ast.Constant)):
            continue
        if test.comparators[0].value == "__main__":
            return node
    return None


def _dotted(node: ast.AST) -> str | None:
    """Return the dotted-attribute string for a Name/Attribute chain, else None.
    e.g. `log_capture._LOG_FILE` -> 'log_capture._LOG_FILE'."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return f"{base}.{node.attr}" if base is not None else None
    return None


# ───────────────────────────────────────────────────────────────────────
# A1 — D1 source-inspection (log_capture.X guard signatures)
# ───────────────────────────────────────────────────────────────────────


def test_a1_main_guard_contains_all_five_tier1_signatures():
    """D1 — the __main__ guard contains all 5 Tier-1 log_capture.X signatures.

    AST-precise: locate the guard If node, unparse its body, verify signatures
    in production code (NOT comment text)."""
    src = _PIPELINE_PATH.read_text(encoding="utf-8")
    assert 'if __name__ == "__main__":' in src, (
        "pipeline.py must contain `if __name__ == \"__main__\":` guard"
    )
    tree = _load_pipeline_ast()
    guard = _find_main_guard_if_node(tree)
    assert guard is not None, "module-level `if __name__ == \"__main__\":` guard not found"
    body_src = "\n".join(ast.unparse(node) for node in guard.body)

    assert "log_capture._archive_terminal_output()" in body_src, (
        "Tier 1.1: log_capture._archive_terminal_output() call missing from guard body"
    )
    assert "log_capture._LOG_FILE = open(" in body_src, (
        "Tier 1.2: log_capture._LOG_FILE = open(...) missing from guard body"
    )
    assert "log_capture._log_drain_thread.start()" in body_src, (
        "Tier 1.3: log_capture._log_drain_thread.start() missing from guard body"
    )
    assert "sys.stdout = log_capture._Tee(" in body_src, (
        "Tier 1.4: sys.stdout = log_capture._Tee(...) missing from guard body"
    )
    assert "Prior session log archived" in body_src, (
        "Tier 1.5: success print missing from guard body"
    )
    # Tier-1 ORDERING (byte-for-byte P0.S12 non-negotiable): _LOG_FILE opened BEFORE the
    # drain thread starts AND before the Tee is installed (both read log_capture._LOG_FILE
    # at runtime). Folded into A1 (not a separate test) to honor the SP-4.1 conservation gate.
    i_open = body_src.index("log_capture._LOG_FILE = open(")
    i_thread = body_src.index("log_capture._log_drain_thread.start()")
    i_tee = body_src.index("sys.stdout = log_capture._Tee(")
    assert i_open < i_thread, "_LOG_FILE must be opened BEFORE the drain thread starts"
    assert i_open < i_tee, "_LOG_FILE must be opened BEFORE the Tee is installed"


# ───────────────────────────────────────────────────────────────────────
# A2 — D2 placeholders now live in runtime/log_capture.py
# ───────────────────────────────────────────────────────────────────────


def test_a2_d2_placeholders_exist_before_main_guard():
    """D2 — `_LOG_FILE = None` + `_archived_log = None` placeholders.

    SP-4.1: these moved pipeline.py -> runtime/log_capture.py (the harness's new home);
    the test now reads log_capture.py. Same D2 purpose — subprocess re-imports get
    None-valued names rather than NameError on attribute access. (Name kept ID-stable.)"""
    src = _LOG_CAPTURE_PATH.read_text(encoding="utf-8")
    assert '_LOG_FILE: "Any" = None' in src, (
        "D2: _LOG_FILE: \"Any\" = None placeholder missing from runtime/log_capture.py"
    )
    assert '_archived_log: "_pathlib.Path | None" = None' in src, (
        "D2: _archived_log placeholder missing from runtime/log_capture.py"
    )


# ───────────────────────────────────────────────────────────────────────
# A3 — D3 source-inspection (inline doc block)
# ───────────────────────────────────────────────────────────────────────


def test_a3_d3_doc_block_at_main_guard():
    """D3 — inline doc block at the guard mentions all anchors + the SP-4.1 rationale."""
    src = _PIPELINE_PATH.read_text(encoding="utf-8")
    doc_header = "P0.S12 — Module-level side-effect guard (Windows-spawn-mode safe boot block)"
    assert doc_header in src, "D3 doc block header missing from pipeline.py"
    doc_start = src.index(doc_header)
    guard_idx = src.index('if __name__ == "__main__":', doc_start)
    doc_window = src[doc_start:guard_idx]

    assert "P0.S12" in doc_window, "D3 doc must reference P0.S12 spec anchor"
    assert "Windows-spawn-mode" in doc_window, "D3 doc must explain Windows-spawn-mode root cause"
    assert "terminal_output_2026-05-27" in doc_window, "D3 doc must name the canary source log"
    # 5-bullet Tier-1 enumeration (log_capture.X forms)
    assert "log_capture._archive_terminal_output()" in doc_window, "5-bullet: archive call"
    assert "log_capture._LOG_FILE = open" in doc_window, "5-bullet: log file open"
    assert "log_capture._log_drain_thread.start()" in doc_window, "5-bullet: daemon start"
    assert "log_capture._Tee" in doc_window, "5-bullet: Tee install"
    assert "Prior session log archived" in doc_window, "5-bullet: success print"
    assert "DO NOT move" in doc_window, "D3 doc must include DO-NOT-MOVE rules"
    # SP-4.1 attribute-rebind rationale + canary-gated note
    assert "attribute-set" in doc_window or "attribute-rebind" in doc_window, (
        "D3 doc must explain the rebound-globals attribute-set rationale"
    )
    assert "canary-gated" in doc_window, "D3 doc must state the boot-rebind is canary-gated"


# ───────────────────────────────────────────────────────────────────────
# A4 — BEHAVIORAL subprocess spawn re-import
# ───────────────────────────────────────────────────────────────────────


def _stub_sounddevice_in_subprocess() -> None:
    """Stub sounddevice in subprocess sys.modules BEFORE importing pipeline."""
    import sys as _sys
    import types as _types
    from unittest.mock import MagicMock as _MagicMock
    if "sounddevice" not in _sys.modules:
        _sd = _types.ModuleType("sounddevice")
        _sd.InputStream = _MagicMock()
        _sd.OutputStream = _MagicMock()
        _sd.play = _MagicMock()
        _sd.wait = _MagicMock()
        _sd.stop = _MagicMock()
        _sd.query_devices = _MagicMock(return_value=[])
        _sd.default = _MagicMock()
        _sys.modules["sounddevice"] = _sd


def _subprocess_import_target() -> int:
    """Spawn subprocess target: import pipeline (guard must NOT run on import) +
    assert log_capture's rebound placeholders are still None."""
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    _stub_sounddevice_in_subprocess()
    import pipeline  # noqa: F401 — triggers the re-export + log_capture import; guard gated
    import runtime.log_capture as _lc
    assert _lc._LOG_FILE is None, (
        f"log_capture._LOG_FILE should be None on subprocess import but got {_lc._LOG_FILE!r}"
    )
    assert _lc._archived_log is None, (
        f"log_capture._archived_log should be None on subprocess import but got {_lc._archived_log!r}"
    )
    return 0


@pytest.mark.slow
def test_a4_spawn_subprocess_imports_pipeline_without_side_effects():
    """D1 behavioral — subprocess spawn re-import of pipeline.py does NOT fire the
    Tier-1 sites; log_capture's _LOG_FILE / _archived_log placeholders stay None."""
    ctx = multiprocessing.get_context("spawn")
    proc = ctx.Process(target=_subprocess_import_target)
    proc.start()
    proc.join(timeout=30)
    assert proc.exitcode == 0, (
        f"subprocess exited with code {proc.exitcode}; expected 0 "
        "(placeholders should hold None; Tier-1 sites should NOT fire on import)"
    )


# ───────────────────────────────────────────────────────────────────────
# A5 — BEHAVIORAL _log_drain importable (re-export survives the move)
# ───────────────────────────────────────────────────────────────────────


def _subprocess_log_drain_importable_target() -> int:
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    _stub_sounddevice_in_subprocess()
    from pipeline import _log_drain  # re-exported from runtime.log_capture
    assert callable(_log_drain), "_log_drain must be importable + callable via pipeline re-export"
    return 0


@pytest.mark.slow
def test_a5_log_drain_importable_in_subprocess_context():
    """D1 behavioral — `from pipeline import _log_drain` still works (SP-4.1 re-export)."""
    ctx = multiprocessing.get_context("spawn")
    proc = ctx.Process(target=_subprocess_log_drain_importable_target)
    proc.start()
    proc.join(timeout=30)
    assert proc.exitcode == 0, (
        f"subprocess could not import _log_drain via pipeline re-export (exit {proc.exitcode})"
    )


# ───────────────────────────────────────────────────────────────────────
# A6 — AST forward-property tripwire (FORALL — every Tier-1 site inside the guard)
# ───────────────────────────────────────────────────────────────────────


def _ids_inside(node: ast.AST) -> set[int]:
    return {id(n) for n in ast.walk(node)}


def test_a6_all_tier1_statements_live_inside_main_guard():
    """D1 forward-property (FORALL) — EVERY Tier-1 statement (log_capture.X attribute
    shape) lives as a descendant of the `if __name__ == "__main__":` guard. Injecting
    a Tier-1 site OUTSIDE the guard (or in the wrong namespace) fires this."""
    tree = _load_pipeline_ast()
    guard = _find_main_guard_if_node(tree)
    assert guard is not None, "module-level `if __name__ == \"__main__\":` guard not found"
    inside = _ids_inside(guard)

    def _assert_forall(matches: list[ast.AST], label: str) -> None:
        assert matches, f"{label}: no matching Tier-1 site found anywhere in pipeline.py"
        for node in matches:
            assert id(node) in inside, (
                f"{label}: a matching Tier-1 site lives OUTSIDE the __main__ guard "
                "(D1 invariant — every Tier-1 side-effect must be guarded)"
            )

    # Tier 1.1 — log_capture._archived_log = log_capture._archive_terminal_output()
    t11 = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Assign) and len(n.targets) == 1
        and _dotted(n.targets[0]) == "log_capture._archived_log"
        and isinstance(n.value, ast.Call)
        and _dotted(n.value.func) == "log_capture._archive_terminal_output"
    ]
    _assert_forall(t11, "Tier 1.1 archive call")

    # Tier 1.2 — log_capture._LOG_FILE = open(...)
    t12 = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Assign) and len(n.targets) == 1
        and _dotted(n.targets[0]) == "log_capture._LOG_FILE"
        and isinstance(n.value, ast.Call) and _dotted(n.value.func) == "open"
    ]
    _assert_forall(t12, "Tier 1.2 _LOG_FILE open")

    # Tier 1.3 — log_capture._log_drain_thread.start()
    t13 = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and _dotted(n.func) == "log_capture._log_drain_thread.start"
    ]
    _assert_forall(t13, "Tier 1.3 thread start")

    # Tier 1.4 — sys.stdout/stderr = log_capture._Tee(...)
    t14 = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Assign) and len(n.targets) == 1
        and _dotted(n.targets[0]) in ("sys.stdout", "sys.stderr")
        and isinstance(n.value, ast.Call) and _dotted(n.value.func) == "log_capture._Tee"
    ]
    _assert_forall(t14, "Tier 1.4 Tee install")

    # Tier 1.5 — print("[Pipeline] ... Prior session log archived ...")
    def _print_has_archived(node: ast.AST) -> bool:
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print"):
            return False
        for arg in node.args:
            if isinstance(arg, ast.JoinedStr):
                for v in arg.values:
                    if isinstance(v, ast.Constant) and isinstance(v.value, str) and "Prior session log archived" in v.value:
                        return True
            elif isinstance(arg, ast.Constant) and isinstance(arg.value, str) and "Prior session log archived" in arg.value:
                return True
        return False

    t15 = [n for n in ast.walk(tree) if _print_has_archived(n)]
    _assert_forall(t15, "Tier 1.5 success print")
