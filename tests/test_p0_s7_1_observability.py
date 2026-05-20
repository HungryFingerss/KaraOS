"""tests/test_p0_s7_1_observability.py — P0.S7.1 SHARED CONTEXT observability.

Spec: tests/p0_s7_1_spec.md (micro-PR, direct-to-developer per user call
2026-05-18 after the P0.S7 canary surfaced the observability gap).

3 logical tests:

  1. test_shared_context_log_emit_per_outcome  (parametrized A-F = 6 cases)
     — _build_shared_context_block emits exactly one [SharedContext] line
       per outcome path with the locked format string.

  2. test_brain_context_summary_includes_shared_context_field
     — `[Brain] Context:` summary log line ends with `shared_context=<N>`
       reflecting the module-level _last_shared_context_row_count.

  3. test_last_shared_context_row_count_module_attr
     — AST scan asserts _last_shared_context_row_count is assigned on
       every code path in _build_shared_context_block.
"""
from __future__ import annotations

import ast
import pathlib
from unittest.mock import MagicMock, patch

import pytest


_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
_PIPELINE_PY = _REPO_ROOT / "pipeline.py"


# ────────────────────────────────────────────────────────────────────────────
# Test 1 — log emit per outcome path (parametrized A-F = 6 cases)
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "scenario,expected_substr",
    [
        # Path A — flag off.
        ("flag_off",       "[SharedContext] gate=flag_off"),
        # Path B — single-person session (count<2). P0.S7.5 D2 widened
        # the gate to also try recent-audience fallback; when no recent
        # rooms exist (mock returns []), the log line is the compound
        # gate=single_person + no_recent_audience.
        ("single_person",  "gate=single_person + no_recent_audience"),
        # Path C — room_session_id empty/None. P0.S7.5 D2 routes this
        # through the same fallback; with no recent rooms it logs
        # gate=single_person + no_recent_audience (the fallback handles
        # BOTH single_person AND no-room cases uniformly).
        ("no_room",        "gate=single_person + no_recent_audience"),
        # Path D — disputed caller.
        ("disputed",       "[SharedContext] gate=disputed"),
        # Path E — DB returned 0 rows.
        ("zero_rows",      "rows=0 → skip"),
        # Path F — DB returned N rows; rendered.
        ("rendered",       "→ rendered"),
    ],
)
def test_shared_context_log_emit_per_outcome(scenario, expected_substr, capsys):
    """Each of the 6 outcome paths emits exactly one [SharedContext] log
    line matching the locked format. Used by the canary grep checks per
    `tests/p0_s7_1_canary_runbook.md`."""
    import pipeline

    db = MagicMock()
    # P0.S7.5 D2 — single_person + no_room scenarios now route through
    # the D2 fallback branch (get_recent_audience_rooms). Configure the
    # mock to return [] so the fallback hits the no-recent-rooms path
    # and emits a deterministic compound gate log line.
    db.get_recent_audience_rooms.return_value = []
    # Configure DB rows per scenario.
    if scenario == "rendered":
        fake_rows = [
            {"person_id": "lexi_xyz", "role": "user",
             "text": "hi", "ts": 1779010000.0,
             "audience_ids": ["jagan_001", "lexi_xyz"], "addressed_to": None},
        ]
        db.get_recent_room_conversation.return_value = fake_rows
        db.get_person.return_value = {"name": "Lexi"}
    else:
        db.get_recent_room_conversation.return_value = []

    # Build kwargs that fire each gate exclusively.
    kwargs = dict(
        room_session_id="room_obs",
        requester_pid="jagan_001",
        best_friend_id=None,
        db=db,
        is_disputed_fn=lambda pid: False,
        active_session_count=2,
        limit=10,
        now=1779010100.0,
    )
    if scenario == "flag_off":
        with patch.object(pipeline, "SHARED_CONTEXT_BLOCK_ENABLED", False):
            pipeline._build_shared_context_block(**kwargs)
    elif scenario == "single_person":
        kwargs["active_session_count"] = 1
        pipeline._build_shared_context_block(**kwargs)
    elif scenario == "no_room":
        kwargs["room_session_id"] = None
        pipeline._build_shared_context_block(**kwargs)
    elif scenario == "disputed":
        kwargs["is_disputed_fn"] = lambda pid: True
        pipeline._build_shared_context_block(**kwargs)
    elif scenario == "zero_rows":
        pipeline._build_shared_context_block(**kwargs)
    else:  # rendered
        pipeline._build_shared_context_block(**kwargs)

    captured = capsys.readouterr().out
    # Exactly ONE matching [SharedContext] line per call.
    matching_lines = [
        ln for ln in captured.splitlines()
        if "[SharedContext]" in ln and expected_substr in ln
    ]
    assert len(matching_lines) == 1, (
        f"Path {scenario!r}: expected exactly one [SharedContext] log line "
        f"containing {expected_substr!r}; found {len(matching_lines)}.\n"
        f"Full stdout:\n{captured}"
    )


# ────────────────────────────────────────────────────────────────────────────
# Test 2 — [Brain] Context summary line includes shared_context=<N>
# ────────────────────────────────────────────────────────────────────────────


def test_brain_context_summary_format_includes_shared_context_field():
    """Source-inspection — the `[Brain] Context:` print(...) format string in
    conversation_turn ends with the new `shared_context={_last_shared_context_
    row_count}` field. Preserves existing field order (history / memory /
    emotion / room / scene) by appending."""
    src = _PIPELINE_PY.read_text(encoding="utf-8")
    # Locate the [Brain] Context: print line.
    ctx_lines = [ln for ln in src.splitlines() if "[Brain] Context: history=" in ln]
    assert len(ctx_lines) == 1, (
        f"Expected exactly one `[Brain] Context: history=...` print site in "
        f"pipeline.py; found {len(ctx_lines)}."
    )
    line = ctx_lines[0]
    # All five legacy fields preserved in order.
    for legacy in ("history=", "memory=", "emotion=", "room=", "scene="):
        assert legacy in line, (
            f"P0.S7.1 must EXTEND the summary line (not reorder); legacy "
            f"field {legacy!r} missing."
        )
    # New field present + sourced from the module-level row-count attr.
    assert "shared_context=" in line, (
        "P0.S7.1: [Brain] Context: summary line must include "
        "`shared_context=<N>` field"
    )
    assert "_last_shared_context_row_count" in line, (
        "P0.S7.1: shared_context value must reference the module-level "
        "_last_shared_context_row_count (set on every _build_shared_context"
        "_block code path) — not a stale local."
    )


def test_brain_context_summary_renders_row_count_at_runtime(capsys):
    """Behavioral — after calling _build_shared_context_block with a 3-row
    render, the module attr reads 3; after a skip path, it resets to 0.
    Validates the module attr is the right source for the summary line."""
    import pipeline

    # 3-row render path.
    db = MagicMock()
    db.get_recent_room_conversation.return_value = [
        {"person_id": "lexi_xyz", "role": "user", "text": "a",
         "ts": 1779010000.0, "audience_ids": ["lexi_xyz", "jagan_001"],
         "addressed_to": None},
        {"person_id": "jagan_001", "role": "assistant", "text": "b",
         "ts": 1779010001.0, "audience_ids": ["lexi_xyz", "jagan_001"],
         "addressed_to": None},
        {"person_id": "lexi_xyz", "role": "user", "text": "c",
         "ts": 1779010002.0, "audience_ids": ["lexi_xyz", "jagan_001"],
         "addressed_to": None},
    ]
    db.get_person.return_value = {"name": "Lexi"}
    pipeline._build_shared_context_block(
        room_session_id="room_x", requester_pid="jagan_001",
        best_friend_id=None, db=db, is_disputed_fn=lambda pid: False,
        active_session_count=2, limit=10, now=1779010100.0,
    )
    assert pipeline._last_shared_context_row_count == 3

    # Skip path — module attr resets to 0.
    pipeline._build_shared_context_block(
        room_session_id="room_x", requester_pid="jagan_001",
        best_friend_id=None, db=db, is_disputed_fn=lambda pid: False,
        active_session_count=1,  # single-person → skip
        limit=10, now=1779010100.0,
    )
    assert pipeline._last_shared_context_row_count == 0, (
        "Module attr must reset to 0 on EVERY skip path so the summary line "
        "doesn't carry a stale row count across turns."
    )


# ────────────────────────────────────────────────────────────────────────────
# Test 3 — AST: _last_shared_context_row_count assigned on every return path
# ────────────────────────────────────────────────────────────────────────────


def test_last_shared_context_row_count_assigned_on_every_return_path():
    """Walk the AST of build_shared_context_block. For every `Return` node
    (skip paths) AND for the implicit fall-through path (final render),
    assert that `_last_shared_context_row_count` is assigned somewhere
    along the path. The stale-value bug class: a future refactor adds a new
    return path but forgets to set the module attr, and the next turn's
    summary line carries the previous turn's row count.

    P0.S7.D-D: body moved from pipeline.py:_build_shared_context_block
    to core/room_orchestrator.py::RoomOrchestrator.build_shared_context_block.
    AST scan redirected to the class-method file accordingly.
    """
    _ROOM_ORCH_PY = _PIPELINE_PY.parent / "core" / "room_orchestrator.py"
    src = _ROOM_ORCH_PY.read_text(encoding="utf-8")
    tree = ast.parse(src)

    fn_node = None
    for node in ast.walk(tree):
        if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == "build_shared_context_block"):
            fn_node = node
            break
    assert fn_node is not None, "build_shared_context_block missing"

    # Annotate parents for ancestor-walking.
    for node in ast.walk(fn_node):
        for child in ast.iter_child_nodes(node):
            child._parent = node  # type: ignore[attr-defined]

    # Find every Return statement.
    returns = [n for n in ast.walk(fn_node) if isinstance(n, ast.Return)]
    assert returns, "_build_shared_context_block must have at least one Return"

    # Find every assignment to _last_shared_context_row_count.
    # P0.S7.D-D: class method writes via late `import pipeline as _pl`
    # so target is `_pl._last_shared_context_row_count` (ast.Attribute).
    # Legacy module-level function used bare ast.Name target. Accept
    # either shape.
    assignments_to_attr: list[int] = []
    for n in ast.walk(fn_node):
        if isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name) and t.id == "_last_shared_context_row_count":
                    assignments_to_attr.append(n.lineno)
                elif isinstance(t, ast.Attribute) and t.attr == "_last_shared_context_row_count":
                    assignments_to_attr.append(n.lineno)

    # Every return statement must have at least one assignment to the attr
    # in a strictly-prior line in the enclosing function. This isn't a
    # perfect dataflow analysis (a refactor that puts the assignment in a
    # branch the return doesn't fall through would slip), but it catches
    # the common drift: adding a `return None` without setting the attr.
    violations: list[str] = []
    for ret in returns:
        prior_assigns = [a for a in assignments_to_attr if a < ret.lineno]
        if not prior_assigns:
            violations.append(
                f"_build_shared_context_block return at line {ret.lineno}: "
                f"no preceding `_last_shared_context_row_count = ...` "
                f"assignment in this function. Add the assignment or the "
                f"caller's summary line will carry a stale row count."
            )
    assert violations == [], (
        "P0.S7.1 module-attr invariant violations:\n"
        + "\n".join(violations)
    )

    # Also: at least 6 assignments total (1 per outcome path: A/B/C/D/E + F).
    # Counts the structural code paths through the function.
    assert len(assignments_to_attr) >= 6, (
        f"Expected ≥6 assignments to _last_shared_context_row_count in "
        f"_build_shared_context_block (one per outcome path); found "
        f"{len(assignments_to_attr)}."
    )
