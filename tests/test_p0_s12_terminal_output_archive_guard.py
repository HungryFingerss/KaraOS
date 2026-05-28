"""P0.S12 — terminal_output.md PermissionError on multiprocessing.spawn re-import.

6 anchors per Plan v1 §3 LOCK at exact mid 6 (inclusive ±15% band [5.1, 6.9]):

  A1 — D1 source-inspection: `if __name__ == "__main__":` block exists in pipeline.py
       AND contains all 5 Tier 1 site signatures (archive call, _LOG_FILE open,
       daemon thread start, _Tee install, success print).
  A2 — D2 source-inspection: module-level `_LOG_FILE = None` placeholder exists
       BEFORE the __main__ guard.
  A3 — D3 source-inspection: inline doc block at the guard mentions all anchors
       (P0.S12, Windows-spawn-mode, terminal_output_2026-05-27, 5-bullet Tier 1).
  A4 — BEHAVIORAL subprocess spawn re-import: `multiprocessing.get_context("spawn")`
       runs `_subprocess_import_target`; subprocess imports pipeline + asserts
       _LOG_FILE is None + _archived_log is None + exits 0; parent terminal_output.md
       handle stays valid.
  A5 — BEHAVIORAL _log_drain function still importable in subprocess context.
       NameError on _LOG_FILE fires only when CALLED, not at import — daemon thread
       only started in main.
  A6 — AST forward-property tripwire: walk pipeline.py AST; assert all 5 Tier 1
       statements (Call of _archive_terminal_output, Assign of _LOG_FILE = open(...),
       Call of _log_drain_thread.start, Assign of sys.stdout = _Tee(...), conditional
       print) live as descendants of the `if __name__ == "__main__":` If node — NOT
       at module top level. Catches future refactors that accidentally move a Tier 1
       site back outside the guard.

Spec: tests/p0_s12_terminal_output_archive_guard_plan_v1.md
"""
from __future__ import annotations

import ast
import multiprocessing
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_PIPELINE_PATH = _REPO_ROOT / "pipeline.py"


# ───────────────────────────────────────────────────────────────────────
# Shared helpers — locate the __main__ guard If node + Tier 1 sites
# ───────────────────────────────────────────────────────────────────────


def _load_pipeline_ast() -> ast.Module:
    return ast.parse(_PIPELINE_PATH.read_text(encoding="utf-8"))


def _find_main_guard_if_node(tree: ast.Module) -> ast.If | None:
    """Return the `if __name__ == "__main__":` If node at module top level."""
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


# ───────────────────────────────────────────────────────────────────────
# A1 — D1 source-inspection
# ───────────────────────────────────────────────────────────────────────


def test_a1_main_guard_contains_all_five_tier1_signatures():
    """D1 — `if __name__ == "__main__":` block must exist in pipeline.py AND
    contain all 5 Tier 1 site signatures.

    A1 STRENGTHENED at Phase 5 regression (a) — substring `_archive_terminal_output()`
    matched against the D3 doc block's enumeration bullet even when the
    real Call site was removed. Tightened to slice the guard body via AST
    `ast.unparse` so substrings are checked in production code, NOT comment
    text. Same family-shape as P0.R8 A2 + P0.R10 A6 + P0.R12-R15 A3 + P0.S11 A5
    strengthenings under `### Induction-surfaces-invariant-gaps` operational rule 3.
    """
    src = _PIPELINE_PATH.read_text(encoding="utf-8")
    assert 'if __name__ == "__main__":' in src, (
        "pipeline.py must contain `if __name__ == \"__main__\":` guard"
    )

    # AST-precise: locate the P0.S12 D1 guard If node, unparse its body,
    # then verify Tier 1 signatures exist in the production code (NOT comment text).
    tree = _load_pipeline_ast()
    guard = _find_main_guard_if_node(tree)
    assert guard is not None, "module-level `if __name__ == \"__main__\":` guard not found"
    body_src = "\n".join(ast.unparse(node) for node in guard.body)

    # 5 Tier 1 signatures — all must appear in the guard's UNPARSED body
    assert "_archive_terminal_output()" in body_src, (
        "Tier 1.1: _archive_terminal_output() call missing from guard body"
    )
    assert "_LOG_FILE = open(" in body_src, (
        "Tier 1.2: _LOG_FILE = open(...) assignment missing from guard body"
    )
    assert "_log_drain_thread.start()" in body_src, (
        "Tier 1.3: _log_drain_thread.start() missing from guard body"
    )
    assert "sys.stdout = _Tee(" in body_src, (
        "Tier 1.4: sys.stdout = _Tee(...) missing from guard body"
    )
    assert "Prior session log archived" in body_src, (
        "Tier 1.5: success print missing from guard body"
    )


# ───────────────────────────────────────────────────────────────────────
# A2 — D2 source-inspection (placeholders BEFORE guard)
# ───────────────────────────────────────────────────────────────────────


def test_a2_d2_placeholders_exist_before_main_guard():
    """D2 — Module-level `_LOG_FILE = None` and `_archived_log = None`
    placeholders MUST exist BEFORE the __main__ guard so subprocess
    re-imports get None-valued names rather than NameError.
    """
    src = _PIPELINE_PATH.read_text(encoding="utf-8")
    # rindex (not index) because the literal `if __name__ == "__main__":`
    # appears earlier in the D2 comment text ("Real values assigned in the
    # `if __name__ == "__main__":` guard below."). rindex finds the ACTUAL
    # guard line, not the comment occurrence.
    guard_idx = src.rindex('if __name__ == "__main__":')
    before_guard = src[:guard_idx]

    # Both D2 placeholder assignments present BEFORE the guard
    assert "_LOG_FILE: \"Any\" = None" in before_guard or \
           '_LOG_FILE: "Any" = None' in before_guard, (
        "D2: _LOG_FILE: \"Any\" = None placeholder missing BEFORE guard"
    )
    assert '_archived_log: "_pathlib.Path | None" = None' in before_guard, (
        "D2: _archived_log placeholder missing BEFORE guard"
    )
    # Spec-anchor comment present
    assert "P0.S12 D2" in before_guard, "D2 comment must reference spec anchor"


# ───────────────────────────────────────────────────────────────────────
# A3 — D3 source-inspection (inline doc block)
# ───────────────────────────────────────────────────────────────────────


def test_a3_d3_doc_block_at_main_guard():
    """D3 — Inline doc block at the __main__ guard MUST mention all anchors:
    P0.S12, Windows-spawn-mode, terminal_output_2026-05-27, 5-bullet Tier 1
    enumeration, and DO-NOT-MOVE rules for Tier 2/3 isolation.

    Locate the P0.S12 D1 guard by anchoring on the doc-block header line
    (NOT by rindex on the guard literal — pipeline.py has TWO real
    `if __name__ == "__main__":` blocks: the P0.S12 D1 guard around Tier 1
    sites + the entry-point block at file end that runs asyncio.run(run())).
    """
    src = _PIPELINE_PATH.read_text(encoding="utf-8")
    # The D3 doc block opens with a distinctive header line; find it directly.
    doc_header = "# P0.S12 — Module-level side-effect guard (Windows-spawn-mode safe boot block)"
    assert doc_header in src, "D3 doc block header missing from pipeline.py"
    doc_start = src.index(doc_header)
    # The guard line that this doc precedes is the FIRST `if __name__ == "__main__":`
    # after the doc header.
    guard_idx = src.index('if __name__ == "__main__":', doc_start)
    doc_window = src[doc_start:guard_idx]

    assert "P0.S12" in doc_window, "D3 doc must reference P0.S12 spec anchor"
    assert "Windows-spawn-mode" in doc_window, (
        "D3 doc must explain Windows-spawn-mode root cause"
    )
    assert "terminal_output_2026-05-27" in doc_window, (
        "D3 doc must name the canary source-of-truth log file"
    )
    # 5-bullet Tier 1 enumeration — all 5 names must appear
    assert "_archive_terminal_output()" in doc_window, "5-bullet: archive call"
    assert "_LOG_FILE = open" in doc_window, "5-bullet: log file open"
    assert "_log_drain_thread.start()" in doc_window, "5-bullet: daemon start"
    assert "_Tee" in doc_window, "5-bullet: Tee install"
    assert "Prior session log archived" in doc_window, "5-bullet: success print"
    # DO-NOT-MOVE rules
    assert "DO NOT move" in doc_window, (
        "D3 doc must include DO-NOT-MOVE Tier 1/2/3 rules"
    )


# ───────────────────────────────────────────────────────────────────────
# A4 — BEHAVIORAL subprocess spawn re-import
# ───────────────────────────────────────────────────────────────────────


def _stub_sounddevice_in_subprocess() -> None:
    """Stub sounddevice in subprocess sys.modules BEFORE importing pipeline.

    sounddevice is not installable on Windows dev (driver dependency); pipeline
    imports core.audio which imports sounddevice. Stubbing lets the subprocess
    test exercise the spawn-mode D1 guard without infra dependency.
    """
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
    """Spawn subprocess target: import pipeline + assert D2 placeholders are None.

    Must be at module level (not nested) so multiprocessing.spawn can pickle it
    by name. Returns 0 on clean assertion pass; raises AssertionError otherwise
    (subprocess exits with non-zero code via the multiprocessing.Process
    exception-propagation mechanism).
    """
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    _stub_sounddevice_in_subprocess()
    import pipeline as _pl
    assert _pl._LOG_FILE is None, (
        f"_LOG_FILE should be None in subprocess but got {_pl._LOG_FILE!r}"
    )
    assert _pl._archived_log is None, (
        f"_archived_log should be None in subprocess but got {_pl._archived_log!r}"
    )
    return 0


@pytest.mark.slow
def test_a4_spawn_subprocess_imports_pipeline_without_side_effects():
    """D1 behavioral — subprocess spawn re-import of pipeline.py does NOT
    fire Tier 1 sites (archive call, _LOG_FILE open, daemon thread start,
    Tee install, success print). Parent's terminal_output.md handle stays
    valid (size unchanged across the subprocess spawn).
    """
    ctx = multiprocessing.get_context("spawn")
    proc = ctx.Process(target=_subprocess_import_target)
    proc.start()
    proc.join(timeout=30)
    assert proc.exitcode == 0, (
        f"subprocess exited with code {proc.exitcode}; expected 0 "
        "(D2 placeholders should hold; Tier 1 sites should NOT fire)"
    )


# ───────────────────────────────────────────────────────────────────────
# A5 — BEHAVIORAL _log_drain importable in subprocess
# ───────────────────────────────────────────────────────────────────────


def _subprocess_log_drain_importable_target() -> int:
    """Spawn subprocess target: verify _log_drain is importable post-D1.

    The function lives at module level (not inside the __main__ guard) so it
    must be importable in subprocess context. NameError on _LOG_FILE only
    fires if _log_drain is actually CALLED — which subprocess never does
    because _log_drain_thread.start() is gated.
    """
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    _stub_sounddevice_in_subprocess()
    from pipeline import _log_drain
    assert callable(_log_drain), "_log_drain must be importable + callable"
    return 0


@pytest.mark.slow
def test_a5_log_drain_importable_in_subprocess_context():
    """D1 behavioral — _log_drain function definition stays at module level
    (NOT inside __main__ guard), so subprocess can import it. The function
    references _LOG_FILE at CALL time, not def time, so import succeeds even
    when _LOG_FILE is None.
    """
    ctx = multiprocessing.get_context("spawn")
    proc = ctx.Process(target=_subprocess_log_drain_importable_target)
    proc.start()
    proc.join(timeout=30)
    assert proc.exitcode == 0, (
        f"subprocess could not import _log_drain (exit {proc.exitcode}); "
        "D1 must keep _log_drain def at module level"
    )


# ───────────────────────────────────────────────────────────────────────
# A6 — AST forward-property tripwire
# ───────────────────────────────────────────────────────────────────────


def test_a6_all_tier1_statements_live_inside_main_guard():
    """D1 forward-property — walk pipeline.py AST; verify all 5 Tier 1
    statements live as DESCENDANTS of the `if __name__ == "__main__":` If
    node (NOT at module top level). Catches future refactors that
    accidentally move a Tier 1 site back outside the guard.
    """
    tree = _load_pipeline_ast()
    guard = _find_main_guard_if_node(tree)
    assert guard is not None, "module-level `if __name__ == \"__main__\":` guard not found"

    # Collect all statements inside the guard body (recursive walk)
    inside_guard: set[int] = set()
    for node in ast.walk(guard):
        inside_guard.add(id(node))

    def _is_inside_guard(node: ast.AST) -> bool:
        return id(node) in inside_guard

    # Tier 1.1 — _archive_terminal_output() call assigned to _archived_log
    # (search for an Assign whose target is Name("_archived_log") AND value is
    # a Call of _archive_terminal_output — the actual deferred-effect site;
    # NOT the D2 None placeholder which is also an Assign to _archived_log).
    found_archive_call = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not (len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "_archived_log"):
            continue
        if not isinstance(node.value, ast.Call):
            continue
        func = node.value.func
        if isinstance(func, ast.Name) and func.id == "_archive_terminal_output":
            assert _is_inside_guard(node), (
                "Tier 1.1: _archived_log = _archive_terminal_output() must "
                "live INSIDE __main__ guard (D1 invariant)"
            )
            found_archive_call = True
            break
    assert found_archive_call, (
        "Tier 1.1: did not find _archived_log = _archive_terminal_output() assignment"
    )

    # Tier 1.2 — _LOG_FILE = open(...) (the real assignment with a Call value,
    # NOT the D2 None placeholder).
    found_log_file_open = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not (len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "_LOG_FILE"):
            continue
        if not isinstance(node.value, ast.Call):
            continue
        func = node.value.func
        if isinstance(func, ast.Name) and func.id == "open":
            # Only the top-level _LOG_FILE = open(_LOG_PATH, "w", ...) at the
            # boot block counts; the rotation helper's _LOG_FILE = open(log_path,...)
            # inside _check_terminal_output_size_cap is a separate site.
            # Distinguish by checking whether the assignment is at module-level
            # OR inside the __main__ guard.
            if _is_inside_guard(node):
                found_log_file_open = True
                break
    assert found_log_file_open, (
        "Tier 1.2: _LOG_FILE = open(...) must live INSIDE __main__ guard "
        "(at least one matching assignment); not found"
    )

    # Tier 1.3 — _log_drain_thread.start() method call
    found_thread_start = False
    for node in ast.walk(guard):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "start":
            continue
        if not isinstance(node.func.value, ast.Name):
            continue
        if node.func.value.id == "_log_drain_thread":
            found_thread_start = True
            break
    assert found_thread_start, (
        "Tier 1.3: _log_drain_thread.start() must live INSIDE __main__ guard"
    )

    # Tier 1.4 — sys.stdout = _Tee(sys.stdout) assignment (search inside guard)
    found_tee_install = False
    for node in ast.walk(guard):
        if not isinstance(node, ast.Assign):
            continue
        if not (len(node.targets) == 1 and isinstance(node.targets[0], ast.Attribute)):
            continue
        target = node.targets[0]
        if not (isinstance(target.value, ast.Name) and target.value.id == "sys"):
            continue
        if target.attr not in ("stdout", "stderr"):
            continue
        # Value is a Call of _Tee
        if not isinstance(node.value, ast.Call):
            continue
        func = node.value.func
        if isinstance(func, ast.Name) and func.id == "_Tee":
            found_tee_install = True
            break
    assert found_tee_install, (
        "Tier 1.4: sys.stdout/stderr = _Tee(...) must live INSIDE __main__ guard"
    )

    # Tier 1.5 — success print() of "[Pipeline] Prior session log archived"
    found_success_print = False
    for node in ast.walk(guard):
        if not isinstance(node, ast.Call):
            continue
        if not (isinstance(node.func, ast.Name) and node.func.id == "print"):
            continue
        # Inspect args for the success substring
        for arg in node.args:
            if isinstance(arg, ast.JoinedStr):
                for value in arg.values:
                    if isinstance(value, ast.Constant) and isinstance(value.value, str):
                        if "Prior session log archived" in value.value:
                            found_success_print = True
                            break
            elif isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                if "Prior session log archived" in arg.value:
                    found_success_print = True
                    break
        if found_success_print:
            break
    assert found_success_print, (
        "Tier 1.5: success print of 'Prior session log archived' must live "
        "INSIDE __main__ guard"
    )
