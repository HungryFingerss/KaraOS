"""tests/test_p0_s7_de.py — P0.S7.D-E γ targeted fix for multi-speaker history.

Plan v2: ``tests/p0_s7_de_plan_v2.md``.

γ adds a helper `_append_per_speaker_history` that fires during the
multi-speaker emit path (pipeline.py:~7060) to append each SECONDARY
speaker's segment text to their own `_conversation_store._history`.
Primary speaker's history is appended by `conversation_turn` with the
combined transcript (existing behavior unchanged).

Without this helper, a secondary speaker's overlap utterance is lost
from their per-person history — so when they take the next primary
turn, their conversation history shows nothing of what they just said
during the multi-speaker burst.

Single-stage fix; no Stage 2 follow-up. γ is additive — if a future
canary surfaces a deeper structural issue, file the full α refactor
as a separate post-canary spec.

Test split per Plan v2 §6.3 canonical numbering:

  Phase 1 (4 tests):
    1. test_append_per_speaker_history_basic — primary delta=0 + secondary +1
    2. test_append_per_speaker_history_dedups_same_pid — same-pid spans collapse
    3. test_append_per_speaker_history_skips_empty_and_none_pid — edge cases
    4. test_spans_with_pids_collected_in_multispeaker_emit — AST forward-property

  Phase 2 (2 tests):
    5. test_append_per_speaker_history_called_from_multispeaker_emit_path — AST
       call-site invariant (gated + exactly-once + located-before-conversation_turn)
    6. test_spans_with_pids_lifetime_within_multispeaker_iteration — D10 AST
       scope-lifetime invariant per Plan v2 §5.3

  Phase 3 (2 tests):
    7a. test_multispeaker_turn_appends_each_speaker_to_own_history[N=2]
    7b. test_multispeaker_turn_appends_each_speaker_to_own_history[N=3]
"""
from __future__ import annotations

import ast
import asyncio
import inspect
import pathlib
import textwrap
import time

import pytest


_PIPELINE_PY = pathlib.Path(__file__).resolve().parent.parent / "pipeline.py"


# ── Phase 1 tests — helper contract + collection AST ────────────────────────


@pytest.mark.asyncio
async def test_append_per_speaker_history_basic():
    """P0.S7.D-E Phase 1 test 1 + Plan v2 §4.3 — BOTH primary delta == 0
    AND secondary delta == +1, explicit before/after row counts.

    The primary-no-double-write invariant is the structural guarantee
    that this helper covers SECONDARY speakers only. If the helper ever
    accidentally appends to the primary's history, the brain would see
    the primary's overlap utterance twice (once from this helper, once
    from conversation_turn). Test 1 catches that drift explicitly.
    """
    import pipeline as _pl

    primary_pid = "jagan_001"
    secondary_pid = "lexi_001"
    await _pl._conversation_store.init_empty(primary_pid)
    await _pl._conversation_store.init_empty(secondary_pid)
    # Seed primary with N existing rows.
    _now = time.time()
    await _pl._conversation_store.append_turns(
        primary_pid, [{"role": "user", "content": "hi", "ts": _now}]
    )
    primary_count_before = len(_pl._conversation_store.peek_history(primary_pid))
    secondary_count_before = len(_pl._conversation_store.peek_history(secondary_pid))

    spans_with_pids = [
        (primary_pid, "Jagan", "hi"),
        (secondary_pid, "Lexi", "hello"),
    ]
    _pl._append_per_speaker_history(
        spans_with_pids, primary_pid=primary_pid, now_ts=time.time(),
    )
    # Fire-and-forget via create_task — flush.
    await asyncio.sleep(0)

    # Primary's row count UNCHANGED (helper skipped primary).
    assert (
        len(_pl._conversation_store.peek_history(primary_pid))
        == primary_count_before
    ), (
        "Helper MUST NOT append to primary_pid's history; "
        "conversation_turn covers primary."
    )
    # Secondary's row count INCREASED by exactly 1.
    assert (
        len(_pl._conversation_store.peek_history(secondary_pid))
        == secondary_count_before + 1
    ), "Helper MUST append exactly 1 row for non-primary speaker"
    # Secondary's appended row has the correct content + role.
    secondary_history = _pl._conversation_store.peek_history(secondary_pid)
    assert secondary_history[-1]["content"] == "hello"
    assert secondary_history[-1]["role"] == "user"


@pytest.mark.asyncio
async def test_append_per_speaker_history_dedups_same_pid():
    """P0.S7.D-E Phase 1 test 2 + Plan v2 §1.5 — STRUCTURAL GUARANTEE of
    the helper's dedup invariant (no longer "belt-and-braces").

    If a future refactor breaks the upstream span-merger's
    consecutive-same-label collapse (pipeline.py:~7018), spans with
    the same pid would arrive at the helper duplicated. The helper's
    seen_pids set MUST collapse them — each speaker gets at most ONE
    history append per multi-speaker turn (Plan v2 §1.4).

    Inverse-check on upstream merger invariant per Plan v2 §1.3.
    """
    import pipeline as _pl

    pid = "lexi_001"
    await _pl._conversation_store.init_empty(pid)
    before = len(_pl._conversation_store.peek_history(pid))

    # Two spans with the same pid — should collapse to ONE history row.
    spans_with_pids = [
        (pid, "Lexi", "first span"),
        (pid, "Lexi", "second span"),
    ]
    _pl._append_per_speaker_history(
        spans_with_pids, primary_pid="jagan_001", now_ts=time.time(),
    )
    await asyncio.sleep(0)

    assert (
        len(_pl._conversation_store.peek_history(pid)) == before + 1
    ), (
        "Dedup invariant violated: same-pid spans MUST collapse to "
        "ONE history row per multi-speaker turn (Plan v2 §1.4)."
    )


@pytest.mark.asyncio
async def test_append_per_speaker_history_skips_empty_and_none_pid():
    """P0.S7.D-E Phase 1 test 3 — edge cases per Plan v2 §1.4 contract.

    Helper MUST skip rows where pid is None (voice ID failed) OR
    content is empty/whitespace-only. Without these skips, the helper
    would either crash on `_conversation_store.append_turns(None, ...)`
    OR pollute a speaker's history with empty rows that the brain
    can't reason about.
    """
    import pipeline as _pl

    real_pid = "lexi_001"
    await _pl._conversation_store.init_empty(real_pid)
    before = len(_pl._conversation_store.peek_history(real_pid))

    spans_with_pids = [
        (None, "unknown_1", "some text"),        # None pid — skipped
        (real_pid, "Lexi", ""),                  # empty content — skipped
        (real_pid, "Lexi", "   \n  "),           # whitespace-only — skipped
        (real_pid, "Lexi", "real content"),      # this one survives
    ]
    _pl._append_per_speaker_history(
        spans_with_pids, primary_pid="jagan_001", now_ts=time.time(),
    )
    await asyncio.sleep(0)

    # Only ONE row appended (the "real content" survivor).
    assert (
        len(_pl._conversation_store.peek_history(real_pid)) == before + 1
    )
    # The surviving row's content is "real content".
    history = _pl._conversation_store.peek_history(real_pid)
    assert history[-1]["content"] == "real content"


def test_spans_with_pids_collected_in_multispeaker_emit():
    """P0.S7.D-E Phase 1 test 4 — AST forward-property.

    `_spans_with_pids` MUST be initialized inside the multi-speaker emit
    block of `run()` (Plan v2 §3 D3 collection lock) AND populated
    inside the same per-span transcription loop that builds
    `_named_pairs`. Without collection, the helper at the call site
    has no rows to append.

    Catches: a future refactor that drops the collection line while
    leaving the helper call in place (helper would no-op silently).
    """
    src = _PIPELINE_PY.read_text(encoding="utf-8")
    tree = ast.parse(src)

    run_fn = None
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "run"
        ):
            run_fn = node
            break
    assert run_fn is not None, "run() function missing from pipeline.py"

    _has_init = False
    _has_append = False
    for inner in ast.walk(run_fn):
        # _spans_with_pids = ... (initialization assignment)
        if isinstance(inner, ast.AnnAssign) or isinstance(inner, ast.Assign):
            _targets = (
                [inner.target] if isinstance(inner, ast.AnnAssign)
                else inner.targets
            )
            for _t in _targets:
                if isinstance(_t, ast.Name) and _t.id == "_spans_with_pids":
                    _has_init = True
        # _spans_with_pids.append(...) call
        if isinstance(inner, ast.Call):
            _f = inner.func
            if (
                isinstance(_f, ast.Attribute)
                and _f.attr == "append"
                and isinstance(_f.value, ast.Name)
                and _f.value.id == "_spans_with_pids"
            ):
                _has_append = True

    assert _has_init, (
        "run() MUST initialize `_spans_with_pids` inside the multi-"
        "speaker emit block (γ collection contract per Plan v2 §3 D3)."
    )
    assert _has_append, (
        "run() MUST populate `_spans_with_pids.append(...)` inside the "
        "per-span transcription loop. Without this, the helper at the "
        "call site has nothing to append per Plan v2 §3 D3."
    )


# ── Phase 2 tests — AST invariants ──────────────────────────────────────────


def test_append_per_speaker_history_called_from_multispeaker_emit_path():
    """P0.S7.D-E Phase 2 test 5 — AST forward-property.

    `_append_per_speaker_history` MUST be called from `run()` exactly
    once AND that call MUST sit inside an `if _multi_speaker_detected:`
    guard AND appear at a strictly LOWER line number than the
    `await conversation_turn(...)` call in the same iteration scope
    (Plan v2 §2.3 — helper fires BEFORE the dispatch so the brain's
    next read sees the appended per-speaker rows).

    Catches: future refactor that drops the call, calls it twice, calls
    it ungated, or moves it AFTER conversation_turn (defeats the purpose).
    """
    src = _PIPELINE_PY.read_text(encoding="utf-8")
    tree = ast.parse(src)

    run_fn = None
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "run"
        ):
            run_fn = node
            break
    assert run_fn is not None, "run() function missing from pipeline.py"

    # Annotate parents for ancestor-walking.
    for parent in ast.walk(run_fn):
        for child in ast.iter_child_nodes(parent):
            child.parent = parent  # type: ignore[attr-defined]

    _helper_call_lines: list[int] = []
    _conversation_turn_lines: list[int] = []
    for inner in ast.walk(run_fn):
        if not isinstance(inner, ast.Call):
            continue
        _f = inner.func
        if isinstance(_f, ast.Name) and _f.id == "_append_per_speaker_history":
            _helper_call_lines.append(inner.lineno)
            # Walk ancestors — find an enclosing `if _multi_speaker_detected:`.
            _has_gate = False
            _cur = getattr(inner, "parent", None)
            while _cur is not None:
                if isinstance(_cur, ast.If):
                    _test_src = ast.unparse(_cur.test)
                    if "_multi_speaker_detected" in _test_src:
                        _has_gate = True
                        break
                _cur = getattr(_cur, "parent", None)
            assert _has_gate, (
                f"_append_per_speaker_history call at line {inner.lineno} "
                "MUST sit inside an `if _multi_speaker_detected:` guard "
                "(Plan v2 §2.3 call-site contract)."
            )
        # await conversation_turn(...) — match the Name pattern.
        if isinstance(_f, ast.Name) and _f.id == "conversation_turn":
            _conversation_turn_lines.append(inner.lineno)

    assert len(_helper_call_lines) == 1, (
        f"_append_per_speaker_history MUST be called exactly once from "
        f"run(); got {len(_helper_call_lines)} call sites at lines "
        f"{_helper_call_lines}. Plan v2 §2.3 locks the single call site."
    )
    assert _conversation_turn_lines, (
        "conversation_turn MUST be invoked from run() (sanity)"
    )
    # The helper call MUST precede the conversation_turn dispatch — helper
    # appends per-speaker rows BEFORE the brain reads history.
    _helper_line = _helper_call_lines[0]
    _later_ct_lines = [l for l in _conversation_turn_lines if l > _helper_line]
    assert _later_ct_lines, (
        f"_append_per_speaker_history at line {_helper_line} MUST precede "
        f"a `conversation_turn(...)` call in the same iteration. "
        f"conversation_turn calls in run(): {_conversation_turn_lines}"
    )


def test_spans_with_pids_lifetime_within_multispeaker_iteration():
    """P0.S7.D-E Phase 2 test 6 (D10) — AST scope-lifetime invariant.

    Plan v2 §5.3 — `_spans_with_pids` MUST be initialized inside the
    multi-speaker emit block AND consumed at the helper call site
    WITHOUT any intervening reset/reassignment (which would silently
    feed the helper a stale or empty list).

    Forward-property: scan `run()`; collect line numbers of every
    `_spans_with_pids = ...` assignment + every
    `_append_per_speaker_history(_spans_with_pids, ...)` call. Assert
    the most recent `_spans_with_pids` assignment BEFORE each helper
    call is the inline initialization (annotated `list[...] = []`) and
    no intervening reset assigns `_spans_with_pids` to a different
    value between the two lines.

    Catches: a future refactor that introduces a new `continue` branch
    or reassigns `_spans_with_pids` between collection and call site.
    Preventive hardening per Plan v2 §5.4 (matches P0.0 S2 tripwire +
    P0.11 _persistent AST tripwire pattern — closes a future-refactor
    surface).
    """
    src = _PIPELINE_PY.read_text(encoding="utf-8")
    tree = ast.parse(src)

    run_fn = None
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "run"
        ):
            run_fn = node
            break
    assert run_fn is not None, "run() function missing from pipeline.py"

    # Collect every assignment line to _spans_with_pids.
    _assignment_lines: list[int] = []
    for inner in ast.walk(run_fn):
        # AnnAssign: `_spans_with_pids: list[...] = []`
        if isinstance(inner, ast.AnnAssign):
            if (
                isinstance(inner.target, ast.Name)
                and inner.target.id == "_spans_with_pids"
            ):
                _assignment_lines.append(inner.lineno)
        # Assign: `_spans_with_pids = X` (no type annotation)
        if isinstance(inner, ast.Assign):
            for _t in inner.targets:
                if isinstance(_t, ast.Name) and _t.id == "_spans_with_pids":
                    _assignment_lines.append(inner.lineno)

    # Collect helper call lines (which use _spans_with_pids as 1st arg).
    _helper_call_lines: list[int] = []
    for inner in ast.walk(run_fn):
        if isinstance(inner, ast.Call):
            _f = inner.func
            if isinstance(_f, ast.Name) and _f.id == "_append_per_speaker_history":
                # Check the first positional arg references _spans_with_pids.
                if inner.args and isinstance(inner.args[0], ast.Name):
                    if inner.args[0].id == "_spans_with_pids":
                        _helper_call_lines.append(inner.lineno)

    assert _assignment_lines, (
        "γ D3 contract: `_spans_with_pids` MUST be initialized in run()."
    )
    assert _helper_call_lines, (
        "γ D4 contract: `_append_per_speaker_history(_spans_with_pids, ...)` "
        "MUST be called in run()."
    )

    # Scope-lifetime: each helper call's most-recent prior assignment is
    # the inline initialization in the multi-speaker block. The invariant
    # we lock: at the present state, there's EXACTLY ONE assignment of
    # `_spans_with_pids` in run() (the init), and it precedes the call.
    # Multiple assignments would indicate a reset/reassignment hazard.
    assert len(_assignment_lines) == 1, (
        f"_spans_with_pids MUST have exactly one assignment in run() "
        f"(the inline init in the multi-speaker emit block). Got "
        f"{len(_assignment_lines)} assignments at lines {_assignment_lines} "
        f"— possible reset/reassignment hazard between init and the "
        f"helper call. Plan v2 §5.3 scope-lifetime invariant violated."
    )
    _init_line = _assignment_lines[0]
    for _call_line in _helper_call_lines:
        assert _init_line < _call_line, (
            f"`_spans_with_pids` init at line {_init_line} MUST precede "
            f"helper call at line {_call_line} — scope-lifetime violated."
        )


# ── Phase 3 tests — behavioral integration parametrized over N ∈ {2, 3} ─────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "n_speakers,case_name",
    [
        (2, "N=2_jagan_lexi"),
        (3, "N=3_jagan_lexi_priya"),
    ],
    ids=["N=2", "N=3"],
)
async def test_multispeaker_turn_appends_each_speaker_to_own_history(
    n_speakers, case_name,
):
    """P0.S7.D-E Phase 3 tests 7a + 7b — behavioral integration over
    N ∈ {2, 3} per Plan v2 §3.

    Constructs a realistic `_spans_with_pids` tuple for a multi-speaker
    turn and invokes `_append_per_speaker_history` directly to verify
    end-to-end: each non-primary speaker gains exactly 1 history row;
    primary's row count is UNCHANGED.

    N=2 and N≥3 take structurally distinct paths through the upstream
    `_format_multispeaker_transcript` per S113 P3B.4 (different header
    formats). γ's helper iterates `_spans_with_pids` independently of
    the transcript format, but the test surface should explicitly cover
    both N=2 and N≥3 to lock the invariant "each non-primary gets their
    own row regardless of N."
    """
    import pipeline as _pl

    # Build N speakers — Jagan primary + (N-1) secondaries.
    primary_pid = "jagan_001"
    secondary_pids = ["lexi_001", "priya_001"][: n_speakers - 1]
    all_pids = [primary_pid] + secondary_pids

    # Init each speaker's history fresh.
    for _pid in all_pids:
        await _pl._conversation_store.init_empty(_pid)

    # Seed each with N existing rows to validate delta assertions
    # against a non-zero baseline (catches "helper accidentally wipes
    # history" class of bug — different shape than zero baseline).
    _now = time.time()
    for _pid in all_pids:
        await _pl._conversation_store.append_turns(
            _pid, [{"role": "user", "content": f"prior turn for {_pid}", "ts": _now}]
        )

    _counts_before = {
        _pid: len(_pl._conversation_store.peek_history(_pid))
        for _pid in all_pids
    }

    # Realistic _spans_with_pids shape: (pid, name, content) per speaker.
    spans_with_pids = [
        (primary_pid, "Jagan", "Hey Lexi, what's up?"),
    ]
    if n_speakers >= 2:
        spans_with_pids.append((secondary_pids[0], "Lexi", "Just thinking about dinner."))
    if n_speakers >= 3:
        spans_with_pids.append((secondary_pids[1], "Priya", "I'm hungry too."))

    _pl._append_per_speaker_history(
        spans_with_pids, primary_pid=primary_pid, now_ts=time.time(),
    )
    # Fire-and-forget — flush.
    await asyncio.sleep(0)

    # Primary's row count UNCHANGED.
    assert (
        len(_pl._conversation_store.peek_history(primary_pid))
        == _counts_before[primary_pid]
    ), (
        f"[{case_name}] Primary's history MUST NOT be touched by helper; "
        "conversation_turn covers primary."
    )
    # Each secondary's row count +1.
    for _sec_pid in secondary_pids:
        assert (
            len(_pl._conversation_store.peek_history(_sec_pid))
            == _counts_before[_sec_pid] + 1
        ), (
            f"[{case_name}] Secondary speaker {_sec_pid!r} MUST gain "
            "exactly 1 history row from this multi-speaker turn."
        )
        # Surviving row content matches the corresponding span.
        _expected_content = next(
            (c for (p, _n, c) in spans_with_pids if p == _sec_pid),
            None,
        )
        _last_row = _pl._conversation_store.peek_history(_sec_pid)[-1]
        assert _last_row["content"] == _expected_content, (
            f"[{case_name}] Secondary {_sec_pid!r} appended content "
            f"mismatch: got {_last_row['content']!r}, expected "
            f"{_expected_content!r}"
        )
        assert _last_row["role"] == "user"
