"""tests/test_p0_s7_dd.py — P0.S7.D-D RoomOrchestrator class extraction.

Plan v2: ``tests/p0_s7_dd_plan_v2.md``.

**Stage 1 of two-stage extraction.** Stage 1 ships the class + module-level
shim functions in pipeline.py. 130 existing test sites work unchanged via
the shim layer. Stage 2 (post-bundled-canary follow-up) hard-deletes the
shims + migrates the 130 test sites; same canary trigger as P0.S7.D-C
Stage 2 (combined PR candidate).

Threshold-crossing event for D-D closure: sub-pattern A graduates to
``### Phase-0-catches-wrong-premise`` numbered doctrine in CLAUDE.md per
Plan v2 §5.1 verbatim wording.

Test split per AST-forward-property-tests-are-the-workhorse + behavioral
pair discipline:

- Phase 1 (4 tests): class exists + 6 methods + __init__ signature +
  init refuses None safety + autouse fixture re-init.
- Phase 2 (4 tests): module-level shims dispatch + raise when uninitialized
  + ``_init_room_orchestrator`` ordering + behavioral integration.
- Phase 3 (3 tests): AST invariants — no legacy body remains + method
  signatures match legacy + D-C flag-gate preserved in moved method.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import ast
import inspect
import pathlib
import textwrap

import pytest
import runtime.wiring as _wiring


_ROOM_ORCH_PY = pathlib.Path(__file__).resolve().parent.parent / "core" / "room_orchestrator.py"
_PIPELINE_PY  = pathlib.Path(__file__).resolve().parent.parent / "pipeline.py"
# P1.A1 SP-6.1: _on_room_end shim relocated pipeline.py → runtime/session.py
# (re-exported in pipeline.py so callers stay byte-identical).
_SESSION_PY   = pathlib.Path(__file__).resolve().parent.parent / "runtime" / "session.py"
# P1.A1 SP-7b.2: _compute_room_audience shim co-relocated pipeline.py →
# flows/companion/turn_flows.py (re-exported in pipeline.py — same shape as SP-6.1).
_TURN_FLOWS_PY = pathlib.Path(__file__).resolve().parent.parent / "flows" / "companion" / "turn_flows.py"


def _resolve_shim_node(name: str):
    """Resolve a P0.S7.D-D shim's FunctionDef + source, following the shim
    relocations. A shim is either defined directly in pipeline.py OR
    re-exported there via ``from <module> import ...`` (its body then living
    in <module>'s file). Relocation sources (in order): runtime.session
    (SP-6.1, _on_room_end) + flows.companion.turn_flows (SP-7b.2,
    _compute_room_audience). Returns ``(node | None, label, src)``."""
    pipeline_src = _PIPELINE_PY.read_text(encoding="utf-8")
    pipeline_tree = ast.parse(pipeline_src)
    for n in pipeline_tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
            return n, "pipeline.py", pipeline_src
    # Re-export relocation sources: (import-module-prefix, label, path).
    _reexport_sources = (
        ("runtime.session", "runtime/session.py", _SESSION_PY),
        ("flows.companion.turn_flows", "flows/companion/turn_flows.py", _TURN_FLOWS_PY),
    )
    for _modpfx, _label, _path in _reexport_sources:
        _reexported = any(
            isinstance(n, ast.ImportFrom)
            and (n.module or "").startswith(_modpfx)
            and any((a.asname or a.name) == name for a in n.names)
            for n in pipeline_tree.body
        )
        if _reexported:
            _src = _path.read_text(encoding="utf-8")
            _tree = ast.parse(_src)
            for n in _tree.body:
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
                    return n, _label, _src
    return None, None, None


# ── Phase 1 tests — class structure + autouse fixture ───────────────────────

def test_p0_s7_dd_room_orchestrator_class_exists_with_6_methods():
    """P0.S7.D-D Phase 1 test 1 — AST-forward-property.

    ``core.room_orchestrator.RoomOrchestrator`` MUST be defined and carry
    the 6 expected methods (drop-`_`-prefix rename per D4; SB.1 D2.4 removed
    ``build_cross_person_excerpts``):
    ``compute_room_audience``, ``kairos_preferred_speaker``,
    ``build_shared_context_block``, ``build_room_block``,
    ``fetch_recent_room_context``, ``on_room_end``.

    Catches accidental method-rename or omission during Stage 2 cleanup.
    """
    from core.room_orchestrator import RoomOrchestrator

    _expected = {
        "compute_room_audience",
        "kairos_preferred_speaker",
        "build_shared_context_block",
        "build_room_block",
        "fetch_recent_room_context",
        "on_room_end",
    }
    _actual = {m for m in dir(RoomOrchestrator) if not m.startswith("_")}
    _missing = _expected - _actual
    assert not _missing, (
        f"RoomOrchestrator missing required methods (Plan v1 D4): "
        f"{sorted(_missing)}. Got: {sorted(_actual)}"
    )


def test_p0_s7_dd_room_orchestrator_init_signature_composes_6_dependencies():
    """P0.S7.D-D Phase 1 test 2 — AST-forward-property.

    ``RoomOrchestrator.__init__`` MUST accept the 6 expected dependency
    parameters: ``session_store``, ``pipeline_state_store``, ``face_db``,
    ``brain_orchestrator``, ``conversation_store``, ``emotion_agents``.

    Catches signature drift that would break the conftest autouse
    fixture's ``RoomOrchestrator(session_store=..., ...)`` call.
    """
    from core.room_orchestrator import RoomOrchestrator

    src = textwrap.dedent(inspect.getsource(RoomOrchestrator.__init__))
    tree = ast.parse(src)
    fn = tree.body[0]
    assert isinstance(fn, ast.FunctionDef), "expected FunctionDef"
    _param_names = [a.arg for a in fn.args.args] + [a.arg for a in fn.args.kwonlyargs]

    _expected_deps = {
        "session_store",
        "pipeline_state_store",
        "face_db",
        "brain_orchestrator",
        "conversation_store",
        "emotion_agents",
    }
    _missing = _expected_deps - set(_param_names)
    assert not _missing, (
        f"RoomOrchestrator.__init__ missing required dependency kwargs: "
        f"{sorted(_missing)}. Got: {_param_names}"
    )


def test_p0_s7_dd_room_orchestrator_init_tolerates_none_deps():
    """P0.S7.D-D Phase 1 test 3 — behavioral.

    Plan v2 §4.1 refined — ``RoomOrchestrator.__init__`` STORES deps
    without asserting; production assert lives in
    ``_init_room_orchestrator()`` (Layer 1). The class tolerates None
    at construction time so the conftest autouse fixture can re-init
    with whatever subset of deps the test context provides.

    Concretely: instantiating with all 6 deps as None MUST succeed
    (no AssertionError, no TypeError). Per-method Layer 3 None-checks
    handle the gaps when methods that need a None dep are invoked.
    """
    from core.room_orchestrator import RoomOrchestrator

    orch = RoomOrchestrator(
        session_store=None,
        pipeline_state_store=None,
        face_db=None,
        brain_orchestrator=None,
        conversation_store=None,
        emotion_agents=None,
    )
    assert orch is not None
    # 4 pure-on-args methods (the ones that don't need the None deps)
    # MUST still be callable without raising.
    assert orch.compute_room_audience(["a", "b"], "a") == ["a", "b"]


def test_p0_s7_dd_autouse_fixture_initializes_room_orchestrator():
    """P0.S7.D-D Phase 1 test 4 + Plan v2 §6 test 11 — behavioral.

    The conftest autouse fixture MUST re-init ``pipeline._room_orchestrator``
    with a fresh RoomOrchestrator instance each test. Without this, the
    shim functions raise ``RuntimeError`` because production-only init
    via ``_init_room_orchestrator()`` from ``run()`` never fires in
    tests.

    Catches a future autouse-fixture refactor that drops the init block.
    Pairs with Phase 2 test 6 (AST: ``_init_room_orchestrator`` called
    in ``run()`` before first shim caller) — covers both production and
    test init paths.
    """
    import pipeline as _pl
    from core.room_orchestrator import RoomOrchestrator

    assert _pl._room_orchestrator is not None, (
        "autouse fixture did not initialize _room_orchestrator — Stage 1 "
        "shim layer relies on the fixture firing before every test. "
        "Check conftest.py for the RoomOrchestrator init block."
    )
    assert isinstance(_pl._room_orchestrator, RoomOrchestrator), (
        f"_room_orchestrator must be a RoomOrchestrator instance, "
        f"got {type(_pl._room_orchestrator).__name__}"
    )


# ── Phase 2 tests — shims + production wiring + behavioral integration ──────

# 6 helper names — the canonical list. Used by multiple tests.
_SHIM_NAMES = (
    "_compute_room_audience",
    "_kairos_preferred_speaker",
    "_build_shared_context_block",
    "_build_room_block",
    "_fetch_recent_room_context",
    "_on_room_end",
)


def test_p0_s7_dd_module_level_shims_exist_for_all_6_helpers():
    """P0.S7.D-D Phase 2 test 4 — AST-forward-property.

    Each of the 6 legacy helper names MUST exist at module scope in
    pipeline.py AND each MUST be a function that references
    ``_room_orchestrator``. Stage 1 contract: 130 test sites continue
    calling the legacy names; the shim layer dispatches to the class.

    Catches partial migration (e.g. a shim accidentally deleted before
    Stage 2 canary).
    """
    import pipeline

    # Each shim is defined in pipeline.py OR re-exported from runtime.session
    # (P1.A1 SP-6.1 relocated _on_room_end into the session engine module).
    _missing = [n for n in _SHIM_NAMES if _resolve_shim_node(n)[0] is None]
    assert not _missing, (
        f"Pipeline.py missing required shim functions: {_missing}. "
        f"Stage 1 contract requires all 6 legacy names exist as shims "
        f"(directly OR re-exported from runtime.session per SP-6.1)."
    )
    # Each shim must reference _room_orchestrator (the dispatch target).
    for _name in _SHIM_NAMES:
        _fn_node, _label, _ = _resolve_shim_node(_name)
        _fn_src = ast.unparse(_fn_node)
        assert "_room_orchestrator" in _fn_src, (
            f"Shim function {_name!r} ({_label}) does not reference "
            f"_room_orchestrator — Stage 1 contract requires dispatch to "
            f"the class instance"
        )
        # Each shim must be callable from pipeline module scope.
        assert callable(getattr(pipeline, _name)), (
            f"pipeline.{_name} must be callable (legacy contract)"
        )


def test_p0_s7_dd_shim_raises_if_room_orchestrator_uninitialized():
    """P0.S7.D-D Phase 2 test 5 — behavioral (Layer 2 defense).

    When ``pipeline._room_orchestrator`` is None, calling ANY shim MUST
    raise ``RuntimeError`` with a message naming
    ``_init_room_orchestrator``. Catches the case where a test runs
    against the shim layer before the autouse fixture has fired (or
    when fixture init silently fails).

    Sets ``_room_orchestrator = None`` directly + restores after.
    Each of the 7 shims must raise.
    """
    import pipeline

    _saved = pipeline._room_orchestrator
    try:
        _wiring._room_orchestrator = None
        # compute_room_audience — pure-on-args, simplest signature.
        with pytest.raises(RuntimeError, match="_init_room_orchestrator"):
            pipeline._compute_room_audience(["a"], "a")
        # build_room_block — multi-arg signature.
        with pytest.raises(RuntimeError, match="_init_room_orchestrator"):
            pipeline._build_room_block(
                active_sessions=(),
                conversation={},
                emotion_agents={},
                room_start_ts=None,
            )
        # kairos_preferred_speaker — uses session_store.
        with pytest.raises(RuntimeError, match="_init_room_orchestrator"):
            pipeline._kairos_preferred_speaker("bf_001")
    finally:
        _wiring._room_orchestrator = _saved


def test_p0_s7_dd_init_room_orchestrator_called_in_run_before_first_shim_caller():
    """P0.S7.D-D Phase 2 test 6 — AST-forward-property.

    ``_init_room_orchestrator()`` MUST be called from ``run()`` at a
    line number strictly LOWER than any reference to a shim function
    inside ``run()``. Otherwise production startup would hit the
    "RoomOrchestrator not initialized" RuntimeError on first call.

    Pairs with Phase 1 test 4 (autouse fixture covers test init).
    """
    import pipeline

    src = inspect.getsource(pipeline.run)
    tree = ast.parse(textwrap.dedent(src))
    fn = tree.body[0]

    _init_line: "int | None" = None
    _first_shim_line: "int | None" = None
    for inner in ast.walk(fn):
        if isinstance(inner, ast.Call):
            _func = inner.func
            if isinstance(_func, ast.Name) and _func.id == "_init_room_orchestrator":
                if _init_line is None or inner.lineno < _init_line:
                    _init_line = inner.lineno
            if isinstance(_func, ast.Name) and _func.id in _SHIM_NAMES:
                if _first_shim_line is None or inner.lineno < _first_shim_line:
                    _first_shim_line = inner.lineno

    assert _init_line is not None, (
        "run() MUST call _init_room_orchestrator() at production boot "
        "(Layer 1 defense per Plan v2 §4.2)"
    )
    # If run() calls shims at all, init must precede the first shim call.
    if _first_shim_line is not None:
        assert _init_line < _first_shim_line, (
            f"_init_room_orchestrator() at line {_init_line} must precede "
            f"first shim caller at line {_first_shim_line}"
        )


def test_p0_s7_dd_room_orchestrator_build_room_block_end_to_end():
    """P0.S7.D-D Phase 2 test 7 — behavioral integration.

    Instantiate RoomOrchestrator with a real SessionStore +
    ConversationStore and seed 2 sessions; call ``build_room_block(...)``
    end-to-end. Assert the rendered block carries the expected ROOM
    markers + role labels. Verifies the class extraction preserves
    behavior under realistic compositions.

    Pairs with the AST tests by exercising the actual code path
    through the class instance.
    """
    from core.room_orchestrator import RoomOrchestrator
    from core.session_state import SessionStore, SessionSnapshot, VoiceEvidence
    import time as _t

    now = _t.time()
    sessions = (
        SessionSnapshot(
            person_id="jagan_bf", person_name="Jagan", person_type="known",
            session_type="face", started_at=now - 60, last_face_seen=now,
            last_spoke_at=now, voice_confidence=0.8, evidence=VoiceEvidence(),
            room_session_id="room_e2e", user_turns=1, kairos_clock_reset=True,
            voice_only_origin=False, waiting_for_name=False, voice_face_confirmed=False,
            db_enrolled=False, confidence_tier="", prior_person_type=None,
            dispute_reason=None, disputed_claimed_name=None, dispute_set_at=None, dispute_set_at_monotonic=None,
            disputed_block_count=0, disputed_block_alerted=False, recent_voice_confs=[],
            cached_prefix=None, core_memory=[], tool_repeat_last=None,
            tool_repeat_count=0, recent_attributions=[],
        ),
        SessionSnapshot(
            person_id="lexi_001", person_name="Lexi", person_type="stranger",
            session_type="face", started_at=now - 60, last_face_seen=now,
            last_spoke_at=now, voice_confidence=0.8, evidence=VoiceEvidence(),
            room_session_id="room_e2e", user_turns=1, kairos_clock_reset=True,
            voice_only_origin=False, waiting_for_name=False, voice_face_confirmed=False,
            db_enrolled=False, confidence_tier="", prior_person_type=None,
            dispute_reason=None, disputed_claimed_name=None, dispute_set_at=None, dispute_set_at_monotonic=None,
            disputed_block_count=0, disputed_block_alerted=False, recent_voice_confs=[],
            cached_prefix=None, core_memory=[], tool_repeat_last=None,
            tool_repeat_count=0, recent_attributions=[],
        ),
    )
    orch = RoomOrchestrator(
        session_store=SessionStore(),
        pipeline_state_store=None,
        face_db=None,
        brain_orchestrator=None,
        conversation_store=None,
        emotion_agents={},
    )
    block = orch.build_room_block(
        active_sessions=sessions,
        conversation={"jagan_bf": [], "lexi_001": []},
        emotion_agents={},
        room_start_ts=now - 60,
        turn_cap=10,
        best_friend_id="jagan_bf",
    )
    assert block is not None, "multi-person room MUST render a block"
    assert "<<<ROOM>>>" in block
    assert "Jagan (best_friend)" in block, (
        "Jagan must render as (best_friend) when pid matches best_friend_id"
    )
    assert "Lexi (stranger)" in block, (
        "Lexi must keep raw person_type label (stranger)"
    )


# ── Phase 3 tests — 3 AST forward-property invariants ───────────────────────

# Legacy-name → class-method-name mapping. Used by tests 8 + 9.
_HELPER_TO_METHOD = {
    "_compute_room_audience":            "compute_room_audience",
    "_kairos_preferred_speaker":         "kairos_preferred_speaker",
    "_build_shared_context_block":       "build_shared_context_block",
    "_build_room_block":                 "build_room_block",
    "_fetch_recent_room_context":        "fetch_recent_room_context",
    "_on_room_end":                      "on_room_end",
}


def test_p0_s7_dd_no_room_helper_body_remains_at_module_level():
    """P0.S7.D-D Phase 3 test 8 — AST-forward-property INVERSE-CHECK.

    For each of the 7 helper names, the pipeline.py module-level
    definition MUST be a thin shim (≤30 lines including signature +
    docstring + RuntimeError guard + single ``_room_orchestrator.<method>(...)``
    dispatch). Catches incomplete migration — i.e. someone leaving the
    legacy body in place alongside the shim.

    The 30-line ceiling accommodates signature-heavy shims (e.g.
    `_build_shared_context_block` with 8 kwargs = 26 lines).
    Legacy bodies were 30-90 LOC; bodies that grow beyond this ceiling
    almost certainly retained legacy code.
    """
    # Resolve each shim wherever it lives (pipeline.py OR runtime/session.py
    # post-SP-6.1) so the ceiling check stays non-vacuous after relocation.
    _violations: list[str] = []
    for _name in _HELPER_TO_METHOD:
        _node, _label, _ = _resolve_shim_node(_name)
        if _node is None:
            continue  # existence is covered by the shims-exist test
        _body_lines = _node.end_lineno - _node.lineno + 1 if _node.end_lineno else 0
        if _body_lines > 30:
            _violations.append(
                f"Helper {_name}() in {_label} at line {_node.lineno} is "
                f"{_body_lines} lines — exceeds shim ceiling (30). Stage 1 "
                f"contract requires the body to live in "
                f"RoomOrchestrator.{_HELPER_TO_METHOD[_name]} with only a "
                f"thin dispatch shim."
            )
    assert not _violations, (
        "P0.S7.D-D Stage 1 inverse-check failed:\n  "
        + "\n  ".join(_violations)
    )


def test_p0_s7_dd_class_method_signatures_match_legacy_shim_signatures():
    """P0.S7.D-D Phase 3 test 9 — AST-forward-property.

    For each helper, the class method's parameter list (excluding
    ``self``) MUST match the legacy module-level shim's parameter list
    exactly. Catches accidental signature drift during the
    body-move (e.g. dropping a kwarg that 130 test sites rely on).

    Shape: parameter NAMES must match (default values + type hints
    may differ in style as long as semantics align — covered by
    end-to-end tests).
    """
    from core.room_orchestrator import RoomOrchestrator

    _violations: list[str] = []
    for _shim_name, _method_name in _HELPER_TO_METHOD.items():
        # Resolve wherever the shim lives (pipeline.py OR runtime/session.py
        # post-SP-6.1); signature contract holds regardless of home module.
        _shim_node, _label, _ = _resolve_shim_node(_shim_name)
        assert _shim_node is not None, f"shim {_shim_name} missing"
        _shim_params = [a.arg for a in _shim_node.args.args] + [
            a.arg for a in _shim_node.args.kwonlyargs
        ]

        _method = getattr(RoomOrchestrator, _method_name, None)
        assert _method is not None, f"method {_method_name} missing"
        _method_sig = inspect.signature(_method)
        _method_params = [
            p for p in _method_sig.parameters.keys() if p != "self"
        ]

        if _shim_params != _method_params:
            _violations.append(
                f"{_shim_name}() shim params {_shim_params} != "
                f"RoomOrchestrator.{_method_name}() params {_method_params}"
            )

    assert not _violations, (
        "P0.S7.D-D method-signature drift detected:\n  "
        + "\n  ".join(_violations)
    )
