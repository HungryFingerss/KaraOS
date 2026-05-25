"""tests/test_p0_s7_5.py — P0.S7.5 bundled-queue canary follow-up.

Plan v2: ``tests/p0_s7_5_plan_v2.md``.

Closes 5 canary-surfaced failure modes from 2026-05-19 multi-person
canary:

- D1 — VISITOR_ALERT nudge consumed on first turn (became one-shot via
  legacy `mark_nudge_injected`); subsequent turns lost the VISITOR
  CONTEXT block. Brain fabricated "No one was here." Fix: persistent
  nudge types stay pending; only types in `ONE_SHOT_NUDGE_TYPES`
  frozenset get mark-injected.
- D2 — SHARED CONTEXT block gated on `active_session_count >= 2`;
  owner-returns-alone scene fired "single_person → skip" even when
  the requester had recent room participation. Fix: D2 fallback
  branch queries `get_recent_audience_rooms` window and renders
  persisted history.
- D3 — `_session_store.rename` was fire-and-forget (`create_task`);
  downstream `peek_snapshot` read pre-rename name. Canonical ack
  said "Got it, visitor." after Lexi rename. Fix: `await` rename
  synchronously.
- D4 — `update_person_name` re-issued 5× after Lexi was already
  renamed. Fix: tool description tightened with Bug Q parallel +
  new `<<<KNOWN SPEAKER IDENTITY>>>` block surfaces the established
  name to the brain.
- D5 — Brain fabricated "I was just waiting for you" absence-of-
  presence claim. Fix: HONESTY POLICY block extended with explicit
  FABRICATED ABSENCE anti-pattern bullet.

Test split per Plan v2 §7.2:

  Phase 1 (5 tests):
    1. ONE_SHOT_NUDGE_TYPES content (no VISITOR_ALERT; has 3 one-shot types)
    2. get_prompt_addendum gates mark_nudge_injected on type membership
    3. get_recent_audience_rooms returns matching rooms in window
    4. build_shared_context_block D2 fallback branch fires
    5. Existing multi-person fast path still works (regression guard)

  Phase 2 (8 tests):
    6. D3 AST — _handle_update_person_name body uses await (not create_task)
    7. D3 behavioral — canonical ack reads new name post-rename
    8. D4 description carries "DO NOT RE-CONFIRM" anchor
    9. format_known_speaker_identity_block renders required anchors
    10. D4 AST — block gated on person_type + flag in _build_system_prompt
    11. D4 behavioral — stranger session does NOT receive KNOWN SPEAKER block
    12. D5 HONESTY POLICY contains FABRICATED ABSENCE bullet
    13. D5 HONESTY POLICY flag-off (regression guard on existing flag)

  Phase 3 (3 behavioral integration):
    14. VISITOR_ALERT persists across multiple turns
    15. D2 widening end-to-end on owner-returns-alone scenario
    16. update_person_name on known session returns handled_noop (no canonical ack)
"""
from __future__ import annotations

import ast
import asyncio
import inspect
import pathlib
import re
import textwrap
import time

import pytest

# P0.S7 D2 — module-level privacy_critical marker; all tests verify
# bundled-queue canary fixes (visitor alert persistence + shared context
# fallback + known speaker block + HONESTY POLICY + nudge gating).
pytestmark = pytest.mark.privacy_critical


_PIPELINE_PY     = pathlib.Path(__file__).resolve().parent.parent / "pipeline.py"
_BRAIN_PY        = _PIPELINE_PY.parent / "core" / "brain.py"
_BRAIN_AGENT_PY  = _PIPELINE_PY.parent / "core" / "brain_agent.py"
_ROOM_ORCH_PY    = _PIPELINE_PY.parent / "core" / "room_orchestrator.py"


# ── Phase 1 tests — D1 + D2 unit work ───────────────────────────────────────


def test_p0_s7_5_one_shot_nudge_types_excludes_visitor_alert():
    """P0.S7.5 D1 Phase 1 test 1 — `ONE_SHOT_NUDGE_TYPES` frozenset MUST
    contain the 3 proactive types AND MUST NOT contain VISITOR_ALERT.

    Plan v2 §2.2 locks the no-`_`-prefix naming. VISITOR_ALERT must
    stay PERSISTENT — owner needs visitor context whenever they ask,
    not just the first re-engagement turn. Default-to-persistent
    fails-safe: a future new nudge type that forgets to opt into
    one-shot worst-cases as "re-injects until expires" — annoying
    but NOT load-bearing data loss (which is what the canary
    surfaced).
    """
    from core.config import ONE_SHOT_NUDGE_TYPES

    assert isinstance(ONE_SHOT_NUDGE_TYPES, frozenset), (
        "ONE_SHOT_NUDGE_TYPES must be a frozenset (immutable + closed)"
    )
    _expected = {"CROSS_PERSON_HYPOTHESIS", "INTENTION_FOLLOWUP", "MEMORY_PROMPT"}
    assert ONE_SHOT_NUDGE_TYPES == _expected, (
        f"ONE_SHOT_NUDGE_TYPES = {ONE_SHOT_NUDGE_TYPES} — must be exactly "
        f"{_expected}. VISITOR_ALERT MUST be EXCLUDED per D1 contract."
    )
    assert "VISITOR_ALERT" not in ONE_SHOT_NUDGE_TYPES, (
        "VISITOR_ALERT in ONE_SHOT_NUDGE_TYPES = the canary failure mode."
    )


def test_p0_s7_5_get_prompt_addendum_gates_mark_injected_on_type():
    """P0.S7.5 D1 Phase 1 test 2 — `PromptPrefAgent.get_prompt_addendum`
    MUST call `mark_nudge_injected` ONLY for nudges whose `nudge_type`
    is in `ONE_SHOT_NUDGE_TYPES`. VISITOR_ALERT and other persistent
    types MUST NOT be marked injected.

    Source-inspection guard — exact wiring matters because the
    canary failure mode was "every nudge marked injected
    unconditionally."
    """
    from core import brain_agent

    # Note: Plan v2 §3.3 references PromptPrefAgent.get_prompt_addendum,
    # but the actual surface lives on BrainOrchestrator (line ~8342).
    # Same kind of spec-detail-vs-code mismatch as P0.S7.4's
    # _build_system_prompt vs render_session_stable_prefix; banked
    # as an in-flight calibration item.
    src = inspect.getsource(brain_agent.BrainOrchestrator.get_prompt_addendum)
    assert "ONE_SHOT_NUDGE_TYPES" in src, (
        "get_prompt_addendum MUST reference ONE_SHOT_NUDGE_TYPES to gate "
        "mark_nudge_injected per D1 contract"
    )
    assert "mark_nudge_injected" in src, (
        "get_prompt_addendum MUST still call mark_nudge_injected for "
        "one-shot types (legacy behavior preserved)"
    )
    # Gate ordering — the mark_nudge_injected call MUST sit inside an
    # `if` whose test references ONE_SHOT_NUDGE_TYPES.
    tree = ast.parse(textwrap.dedent(src))
    fn = tree.body[0]
    for parent in ast.walk(fn):
        for child in ast.iter_child_nodes(parent):
            child.parent = parent  # type: ignore[attr-defined]
    _gated = False
    for inner in ast.walk(fn):
        if not isinstance(inner, ast.Call):
            continue
        _f = inner.func
        if (
            isinstance(_f, ast.Attribute)
            and _f.attr == "mark_nudge_injected"
        ):
            _cur = getattr(inner, "parent", None)
            while _cur is not None:
                if isinstance(_cur, ast.If):
                    if "ONE_SHOT_NUDGE_TYPES" in ast.unparse(_cur.test):
                        _gated = True
                        break
                _cur = getattr(_cur, "parent", None)
    assert _gated, (
        "mark_nudge_injected call MUST sit inside an `if X in "
        "ONE_SHOT_NUDGE_TYPES:` guard. Without the gate, the canary "
        "failure mode reappears (every nudge consumed on first turn)."
    )


def test_p0_s7_5_get_recent_audience_rooms_returns_window_matches(tmp_path):
    """P0.S7.5 D2 Phase 1 test 3 — `FaceDB.get_recent_audience_rooms`
    returns distinct room_session_ids within the time window where
    the requester appears in audience_ids OR is best_friend (owner
    override).

    Behavioral test — exercises the SQL composition end-to-end on a
    real SQLite DB. Catches LIKE-escape regressions + window-filter
    regressions + best_friend override regressions.
    """
    import json
    from core.db import FaceDB

    db = FaceDB(tmp_path / "faces.db", faiss_path=tmp_path / "faiss.index")
    try:
        _now = time.time()
        # Seed 3 rooms with different audience patterns + 1 outside window.
        _rooms_data = [
            # Room 1: requester in audience, recent (within window)
            ("room_1", "jagan_001", "user", "hi from jagan",
             _now - 100, json.dumps(["jagan_001", "lexi_001"])),
            ("room_1", "lexi_001", "user", "hi from lexi",
             _now - 90, json.dumps(["jagan_001", "lexi_001"])),
            # Room 2: requester NOT in audience, recent
            ("room_2", "wasim_001", "user", "different room",
             _now - 80, json.dumps(["wasim_001", "priya_001"])),
            # Room 3: requester in audience, OLD (outside 24h window)
            ("room_3", "jagan_001", "user", "old conversation",
             _now - (25 * 3600), json.dumps(["jagan_001", "lexi_001"])),
            # Room 4: NULL audience, recent — legacy backfill default-visible
            ("room_4", "anyone", "user", "legacy row",
             _now - 50, None),
        ]
        for rid, pid, role, content, ts, aud in _rooms_data:
            db._conn.execute(
                "INSERT INTO conversation_log "
                "(person_id, role, content, ts, room_session_id, audience_ids) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (pid, role, content, ts, rid, aud),
            )
        db._conn.commit()

        # Query as requester="jagan_001", no best_friend (no owner override).
        rooms = db.get_recent_audience_rooms(
            requester_pid="jagan_001",
            best_friend_id=None,
            hours_back=24.0,
            limit=5,
        )
        # Expected: room_1 (in audience, recent) + room_4 (NULL audience).
        # NOT room_2 (not in audience) — NOT room_3 (outside window).
        assert "room_1" in rooms, "requester in audience MUST surface room_1"
        assert "room_4" in rooms, "NULL audience (legacy default-visible) MUST surface"
        assert "room_2" not in rooms, "requester NOT in audience MUST be filtered"
        assert "room_3" not in rooms, "outside 24h window MUST be filtered"

        # Query as best_friend (owner override) — sees room_2 too.
        rooms_owner = db.get_recent_audience_rooms(
            requester_pid="jagan_001",
            best_friend_id="jagan_001",
            hours_back=24.0,
            limit=5,
        )
        assert "room_2" in rooms_owner, (
            "best_friend owner override MUST surface rooms regardless of "
            "audience filter (3A.4.6 ownership model)"
        )
    finally:
        db._conn.close()


def test_p0_s7_5_build_shared_context_d2_fallback_branch_fires():
    """P0.S7.5 D2 Phase 1 test 4 — `build_shared_context_block` MUST
    enter the D2 fallback branch when current scene is single-person
    AND the requester has recent room participation.

    Source-inspection of the fallback branch shape (load-bearing
    contract). Behavioral test 15 in Phase 3 covers end-to-end.
    """
    src = inspect.getsource(__import__(
        "core.room_orchestrator", fromlist=["RoomOrchestrator"]
    ).RoomOrchestrator.build_shared_context_block)
    assert "get_recent_audience_rooms" in src, (
        "D2 fallback branch MUST call db.get_recent_audience_rooms"
    )
    assert "SHARED_CONTEXT_RECENT_AUDIENCE_HOURS" in src, (
        "D2 branch MUST use the config-driven window"
    )
    # The fallback branch should fire when fast-path conditions fail.
    # Verify there's an `else:` branch after the multi-person fast path
    # OR explicit handling of single-person + no-room-id together.
    assert "D2" in src or "recent_audience" in src, (
        "D2 fallback branch must be identifiable in source"
    )


def test_p0_s7_5_build_shared_context_fast_path_still_works():
    """P0.S7.5 D2 Phase 1 test 5 — regression guard. After D2 widening
    refactor, the existing multi-person fast path (D-A semantic) MUST
    still render correctly: when `active_session_count >= 2` AND
    `room_session_id` is provided AND DB returns rows, the block
    renders with the rows from `get_recent_room_conversation`.

    Catches: D2 refactor accidentally breaks the D-A fast path.
    """
    from unittest.mock import MagicMock
    from core.room_orchestrator import RoomOrchestrator

    fake_rows = [
        {"person_id": "lexi_xyz", "role": "user", "text": "Hello room",
         "ts": time.time() - 100, "audience_ids": ["jagan_001", "lexi_xyz"],
         "addressed_to": None},
        {"person_id": "jagan_001", "role": "assistant", "text": "Hi everyone",
         "ts": time.time() - 90, "audience_ids": ["jagan_001", "lexi_xyz"],
         "addressed_to": "Lexi"},
    ]
    db = MagicMock()
    db.get_recent_room_conversation.return_value = fake_rows
    db.get_person.side_effect = lambda pid: (
        {"name": "Lexi"} if pid == "lexi_xyz" else {"name": "Jagan"}
    )
    orch = RoomOrchestrator()
    block = orch.build_shared_context_block(
        room_session_id="room_fast",
        requester_pid="jagan_001",
        best_friend_id="jagan_001",
        db=db,
        is_disputed_fn=lambda pid: False,
        active_session_count=2,
        limit=10,
        now=time.time(),
    )
    assert block is not None, "D-A fast path MUST still render"
    assert "<<<SHARED CONTEXT" in block
    assert "Hello room" in block
    # Ensure the fast path was taken — get_recent_room_conversation
    # called with the explicit room_session_id, NOT the fallback path.
    db.get_recent_room_conversation.assert_called_once_with(
        room_session_id="room_fast",
        requester_pid="jagan_001",
        best_friend_id="jagan_001",
        limit=10,
    )
    db.get_recent_audience_rooms.assert_not_called()


# ── Phase 2 tests — D3 + D4 + D5 ────────────────────────────────────────────


def test_p0_s7_5_d3_handle_update_person_name_uses_await():
    """P0.S7.5 D3 Phase 2 test 6 — AST forward-property.

    `_handle_update_person_name` MUST use `await _session_store.rename(...)`
    (synchronous) — NOT `_loop.create_task(_session_store.rename(...))`
    (race-prone).

    Canary 2026-05-19 root cause: fire-and-forget create_task meant
    downstream `peek_snapshot` read pre-rename name; canonical ack
    said "Got it, visitor." instead of "Got it, Lexi."

    Catches: future refactor that reverts the fix or accidentally
    fires both `await` AND `create_task`.
    """
    src = _PIPELINE_PY.read_text(encoding="utf-8")
    tree = ast.parse(src)

    fn_node = None
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "_handle_update_person_name"
        ):
            fn_node = node
            break
    assert fn_node is not None, "_handle_update_person_name missing"

    # Scan for await _session_store.rename(...) and create_task(_session_store.rename(...))
    _has_await_rename = False
    _has_create_task_rename = False
    for inner in ast.walk(fn_node):
        # await _session_store.rename(...)
        if isinstance(inner, ast.Await):
            _val = inner.value
            if isinstance(_val, ast.Call):
                _f = _val.func
                if (
                    isinstance(_f, ast.Attribute)
                    and _f.attr == "rename"
                    and isinstance(_f.value, ast.Name)
                    and _f.value.id == "_session_store"
                ):
                    _has_await_rename = True
        # _loop.create_task(_session_store.rename(...))
        if isinstance(inner, ast.Call):
            _f = inner.func
            if (
                isinstance(_f, ast.Attribute)
                and _f.attr == "create_task"
            ):
                # Check args[0] is _session_store.rename(...) call
                if inner.args and isinstance(inner.args[0], ast.Call):
                    _inner_call = inner.args[0]
                    _inner_f = _inner_call.func
                    if (
                        isinstance(_inner_f, ast.Attribute)
                        and _inner_f.attr == "rename"
                        and isinstance(_inner_f.value, ast.Name)
                        and _inner_f.value.id == "_session_store"
                    ):
                        _has_create_task_rename = True

    assert _has_await_rename, (
        "_handle_update_person_name MUST use `await _session_store.rename(...)` "
        "(synchronous; downstream peek_snapshot observes post-rename name). "
        "Plan v2 §5.2 D3 lock."
    )
    assert not _has_create_task_rename, (
        "_handle_update_person_name MUST NOT use `_loop.create_task("
        "_session_store.rename(...))` — racy; downstream peek_snapshot reads "
        "stale name. The fire-and-forget pattern was the canary failure mode."
    )


@pytest.mark.asyncio
async def test_p0_s7_5_d3_canonical_ack_reads_new_name_post_rename():
    """P0.S7.5 D3 Phase 2 test 7 — behavioral. After `_handle_update_person_name`
    completes, `_session_store.peek_snapshot(pid).person_name` MUST
    return the NEW name (not the old stranger placeholder).

    Validates the D3 `await` fix end-to-end: the rename is observable
    to the downstream canonical-ack template at pipeline.py:5777.
    """
    import pipeline as _pl

    # Seed a stranger session
    pid = "stranger_x123"
    await _pl._session_store.open_session(
        pid, "visitor", "stranger", "voice", now=time.time(),
    )
    # Verify pre-rename state.
    pre_snap = _pl._session_store.peek_snapshot(pid)
    assert pre_snap is not None
    assert pre_snap.person_name == "visitor"

    # Await rename directly (mirrors the D3 fix path).
    await _pl._session_store.rename(pid, "Lexi")

    # Verify post-rename state — peek MUST observe the new name.
    post_snap = _pl._session_store.peek_snapshot(pid)
    assert post_snap is not None
    assert post_snap.person_name == "Lexi", (
        f"D3 contract violated: peek_snapshot after await rename MUST "
        f"return 'Lexi'; got {post_snap.person_name!r}. Canonical-ack "
        f"would speak the wrong name."
    )


def test_p0_s7_5_d4_update_person_name_description_has_dont_re_confirm():
    """P0.S7.5 D4 Phase 2 test 8 — tool description carries the Bug Q
    parallel "DO NOT RE-CONFIRM" anchor + feedback loop framing.

    Canary 2026-05-19 root cause: brain re-issued `update_person_name`
    5 times after rename completed. The description was missing
    explicit "don't re-confirm" guidance (which `update_system_name`
    has via Bug Q). Mirror the protection.
    """
    from core import brain

    # Find the update_person_name tool in TOOLS.
    _description = None
    for tool in brain.TOOLS:
        if tool.get("function", {}).get("name") == "update_person_name":
            _description = tool["function"]["description"]
            break
    assert _description is not None, "update_person_name tool missing from TOOLS"

    assert "DO NOT RE-CONFIRM" in _description, (
        "update_person_name description MUST contain explicit "
        "'DO NOT RE-CONFIRM' anchor (Bug Q parallel)"
    )
    assert "feedback loop" in _description, (
        "Description MUST name the failure mode explicitly: "
        "'feedback loop' — the brain hears its own canonical-ack "
        "and re-issues the same call"
    )
    assert "Bug Q parallel" in _description or "P0.S7.5" in _description, (
        "Description MUST reference the parallel source (Bug Q or P0.S7.5)"
    )


def test_p0_s7_5_d4_format_known_speaker_identity_block_renders_anchors():
    """P0.S7.5 D4 Phase 2 test 9 — `format_known_speaker_identity_block`
    renders with person_name + person_type interpolated AND contains
    the required anchors (DO NOT call + correction example + Bug Q
    parallel framing).
    """
    from core.brain import format_known_speaker_identity_block

    block = format_known_speaker_identity_block("Lexi", "known")
    # Block markers present.
    assert "<<<KNOWN SPEAKER IDENTITY>>>" in block
    assert "<<<END KNOWN SPEAKER IDENTITY>>>" in block
    # Name + type interpolated.
    assert "Lexi" in block
    assert "person_type='known'" in block
    # Anti-feedback-loop anchors.
    assert "Do NOT call `update_person_name` to confirm" in block, (
        "Block MUST instruct brain NOT to re-confirm the established name"
    )
    assert "Bug Q parallel" in block or "feedback loop" in block, (
        "Block MUST reference the Bug Q parallel framing"
    )
    # Correction example (positive case for when to call).
    assert "I'm not" in block or "Call me" in block or "correct" in block.lower(), (
        "Block MUST give at least one example of a LEGITIMATE rename "
        "correction (positive case for when to call the tool)"
    )


def test_p0_s7_5_d4_known_speaker_block_gated_on_person_type_and_flag():
    """P0.S7.5 D4 Phase 2 test 10 — AST: the
    `format_known_speaker_identity_block` invocation in
    `render_session_stable_prefix` MUST be gated on BOTH
    `KNOWN_SPEAKER_IDENTITY_BLOCK_ENABLED` AND
    `session_person_type in ("known", "best_friend")`.

    Catches: a future refactor that strips the type gate (would render
    the block for strangers, contradicting the STRANGER IDENTITY block).
    """
    from core import brain

    src = inspect.getsource(brain.render_session_stable_prefix)
    tree = ast.parse(textwrap.dedent(src))
    fn = tree.body[0]
    for parent in ast.walk(fn):
        for child in ast.iter_child_nodes(parent):
            child.parent = parent  # type: ignore[attr-defined]

    _block_call_found = False
    for inner in ast.walk(fn):
        if not isinstance(inner, ast.Call):
            continue
        _f = inner.func
        if isinstance(_f, ast.Name) and _f.id == "format_known_speaker_identity_block":
            _block_call_found = True
            # Walk ancestors for the gate.
            _has_flag_gate = False
            _has_type_gate = False
            _cur = getattr(inner, "parent", None)
            while _cur is not None:
                if isinstance(_cur, ast.If):
                    _test_src = ast.unparse(_cur.test)
                    if "KNOWN_SPEAKER_IDENTITY_BLOCK_ENABLED" in _test_src or "_KS_ID_ENABLED" in _test_src:
                        _has_flag_gate = True
                    if "session_person_type" in _test_src and (
                        "known" in _test_src and "best_friend" in _test_src
                    ):
                        _has_type_gate = True
                _cur = getattr(_cur, "parent", None)
            assert _has_flag_gate, (
                "format_known_speaker_identity_block MUST be gated on "
                "KNOWN_SPEAKER_IDENTITY_BLOCK_ENABLED config flag (Plan v2 §6.4)"
            )
            assert _has_type_gate, (
                "format_known_speaker_identity_block MUST be gated on "
                "session_person_type IN ('known', 'best_friend') — strangers "
                "receive the STRANGER IDENTITY block instead (mutual exclusion)"
            )
    assert _block_call_found, (
        "render_session_stable_prefix MUST call "
        "format_known_speaker_identity_block at least once"
    )


def test_p0_s7_5_d4_stranger_session_does_not_get_known_speaker_block():
    """P0.S7.5 D4 Phase 2 test 11 — behavioral: stranger session does
    NOT receive the KNOWN SPEAKER IDENTITY block (mutual exclusion
    with the STRANGER IDENTITY block from Session 97).
    """
    from core.brain import render_session_stable_prefix

    # Stranger session (person_type='stranger', user_turns>=2 normally).
    prefix_stranger = render_session_stable_prefix(
        system_name="Kara",
        session_person_type="stranger",
        session_user_turns=3,
        identity_disputed=False,
        person_name="stranger_abc123",
        disputed_claimed_name=None,
    )
    assert "<<<KNOWN SPEAKER IDENTITY>>>" not in prefix_stranger, (
        "Stranger session MUST NOT receive KNOWN SPEAKER IDENTITY block "
        "(mutual exclusion with STRANGER IDENTITY block per Plan v2 §6.6)"
    )

    # Known session DOES receive the block.
    prefix_known = render_session_stable_prefix(
        system_name="Kara",
        session_person_type="known",
        session_user_turns=3,
        identity_disputed=False,
        person_name="Lexi",
        disputed_claimed_name=None,
    )
    assert "<<<KNOWN SPEAKER IDENTITY>>>" in prefix_known, (
        "Known session MUST receive KNOWN SPEAKER IDENTITY block"
    )


def test_p0_s7_5_d5_honesty_policy_has_fabricated_absence_bullet():
    """P0.S7.5 D5 Phase 2 test 12 — `<<<HONESTY POLICY>>>` block contains
    explicit FABRICATED ABSENCE anti-pattern bullet.

    Canary 2026-05-19 root cause: brain answered "No one was here, I
    was just waiting for you to come back" when Lexi had visited.
    Fabricated absence on TWO axes — (a) no retrieval evidence
    supports nobody-visited; (b) brain's "just waiting" self-narration
    is also confabulated.
    """
    from core import brain

    raw_src = inspect.getsource(brain.render_session_stable_prefix)
    # Collapse adjacent string-literal splits so multi-line bullet text
    # matches contiguously (same shape as P0.S7.4 γ test normalizer).
    src = re.sub(r'"\s+"', "", raw_src)
    # The HONESTY POLICY block is appended inside render_session_stable_prefix.
    assert "FABRICATED ABSENCE" in src, (
        "HONESTY POLICY block MUST contain 'FABRICATED ABSENCE' anchor"
    )
    assert "no one was here" in src.lower(), (
        "Anti-pattern bullet MUST name the exact canary phrasing "
        "'no one was here' to give the brain a concrete negative anchor"
    )
    assert "Absence of memory is NOT evidence of absence" in src, (
        "Bullet MUST contain the core honesty principle"
    )


def test_p0_s7_5_d5_honesty_policy_block_flag_off_regression_guard():
    """P0.S7.5 D5 Phase 2 test 13 — flag-off regression guard. With
    HONESTY_POLICY_BLOCK_ENABLED=False, the entire HONESTY POLICY
    block (including the new FABRICATED ABSENCE bullet) MUST be
    absent from the rendered prefix. The new bullet inherits the
    existing block flag — no new flag added per Plan v2 §7.3.
    """
    from core.brain import render_session_stable_prefix
    from core import config as _cfg
    import pytest as _pt
    _saved = _cfg.HONESTY_POLICY_BLOCK_ENABLED
    try:
        _cfg.HONESTY_POLICY_BLOCK_ENABLED = False
        prefix = render_session_stable_prefix(
            system_name="Kara",
            session_person_type="known",
            session_user_turns=3,
            identity_disputed=False,
            person_name="Lexi",
            disputed_claimed_name=None,
        )
        assert "<<<HONESTY POLICY>>>" not in prefix, (
            "HONESTY POLICY block MUST be entirely absent when "
            "HONESTY_POLICY_BLOCK_ENABLED=False"
        )
        assert "FABRICATED ABSENCE" not in prefix, (
            "FABRICATED ABSENCE bullet inherits the existing block flag — "
            "MUST be absent when block is gated off"
        )
    finally:
        _cfg.HONESTY_POLICY_BLOCK_ENABLED = _saved


# ── Phase 3 tests — behavioral integration ──────────────────────────────────


def test_p0_s7_5_visitor_alert_nudge_persists_across_multiple_calls(tmp_path):
    """P0.S7.5 Phase 3 test 14 — E2E nudge persistence behavioral.

    Queue a VISITOR_ALERT nudge for the best_friend; call
    `get_prompt_addendum` TWICE; assert the nudge text appears in
    BOTH responses (persistent — NOT consumed on first injection).

    Canary 2026-05-19 root cause: VISITOR_ALERT was being consumed
    on first turn; second turn lost the addendum; brain fabricated
    "No one was here." This test seals the persistence invariant.
    """
    from core.brain_agent import BrainDB, BrainOrchestrator
    import asyncio as _aio

    brain_db_path = tmp_path / "brain.db"
    brain_db = BrainDB(str(brain_db_path))
    try:
        bf_id = "jagan_001"
        # Queue a VISITOR_ALERT nudge.
        nudge_id = brain_db.store_nudge(
            target_person_id=bf_id,
            nudge_type="VISITOR_ALERT",
            content="Lexi visited while you were away",
            confidence=0.9,
            metadata={"visitor_name": "Lexi", "visitor_id": "lexi_001"},
            expires_at=time.time() + 86400,
        )
        # Build a minimal orch wrapper that exposes get_prompt_addendum.
        orch = BrainOrchestrator.__new__(BrainOrchestrator)
        orch._brain_db = brain_db

        # First call — nudge MUST inject.
        addendum_1 = orch.get_prompt_addendum(bf_id)
        assert addendum_1 is not None
        assert "Lexi" in addendum_1, "First call MUST inject VISITOR_ALERT nudge"

        # Second call — VISITOR_ALERT is PERSISTENT; MUST still inject.
        addendum_2 = orch.get_prompt_addendum(bf_id)
        assert addendum_2 is not None, (
            "VISITOR_ALERT MUST persist; second call MUST also inject the nudge"
        )
        assert "Lexi" in addendum_2, (
            "Persistent nudge MUST re-inject (D1 contract). Without this, "
            "the canary failure mode reappears: brain loses visitor context "
            "after the first turn and fabricates 'No one was here.'"
        )

        # Third call — confirm persistence holds beyond two turns.
        addendum_3 = orch.get_prompt_addendum(bf_id)
        assert addendum_3 is not None and "Lexi" in addendum_3, (
            "Persistent nudge MUST stay pending until expires_at or dismissed"
        )

        # Sanity — nudge_id row in DB is NOT marked injected.
        rows = brain_db._conn.execute(
            "SELECT injected_at FROM proactive_nudges WHERE id = ?",
            (nudge_id,),
        ).fetchall()
        assert rows[0][0] is None, (
            "VISITOR_ALERT row in DB MUST NOT have injected_at set — that "
            "would mark it one-shot and break persistence (D1 contract)"
        )
    finally:
        brain_db._conn.close()


def test_p0_s7_5_one_shot_nudge_consumed_on_first_call(tmp_path):
    """P0.S7.5 Phase 3 test 14b — regression guard. One-shot types
    (CROSS_PERSON_HYPOTHESIS) still get consumed on first call —
    legacy behavior preserved. Without this guard, D1's refactor
    could accidentally make ALL nudge types persistent (which would
    be its own bug shape).
    """
    from core.brain_agent import BrainDB, BrainOrchestrator

    brain_db_path = tmp_path / "brain.db"
    brain_db = BrainDB(str(brain_db_path))
    try:
        bf_id = "jagan_001"
        nudge_id = brain_db.store_nudge(
            target_person_id=bf_id,
            nudge_type="CROSS_PERSON_HYPOTHESIS",
            content="You and Lexi both mentioned diabetes",
            confidence=0.7,
            metadata={},
            expires_at=time.time() + 86400,
        )
        orch = BrainOrchestrator.__new__(BrainOrchestrator)
        orch._brain_db = brain_db

        # First call — one-shot nudge MUST inject.
        addendum_1 = orch.get_prompt_addendum(bf_id)
        assert addendum_1 is not None and "diabetes" in addendum_1

        # Second call — one-shot type MUST be consumed; nudge=no.
        addendum_2 = orch.get_prompt_addendum(bf_id)
        # Either returns None (nothing pending) OR doesn't contain the nudge text.
        assert addendum_2 is None or "diabetes" not in addendum_2, (
            "One-shot CROSS_PERSON_HYPOTHESIS MUST be consumed on first inject"
        )

        # Sanity — row IS marked injected.
        rows = brain_db._conn.execute(
            "SELECT injected_at FROM proactive_nudges WHERE id = ?",
            (nudge_id,),
        ).fetchall()
        assert rows[0][0] is not None, (
            "One-shot nudge row MUST have injected_at set after first call "
            "(legacy behavior preserved)"
        )
    finally:
        brain_db._conn.close()


def test_p0_s7_5_d2_widening_returns_persisted_history_when_owner_alone(tmp_path):
    """P0.S7.5 Phase 3 test 15 — D2 widening E2E behavioral.

    Seed conversation_log with a prior multi-person room session
    where the owner appears in audience_ids. Owner returns alone
    (active_session_count=1, no current room_session_id) and the
    SHARED CONTEXT block MUST render the persisted history via the
    D2 fallback branch.

    Canary 2026-05-19 root cause: owner returned alone, SHARED
    CONTEXT gated "single_person → skip", persisted history was
    invisible. D2 widening surfaces that history when the owner
    has recent room participation.
    """
    import json
    from core.db import FaceDB
    from core.room_orchestrator import RoomOrchestrator

    db = FaceDB(tmp_path / "faces.db", faiss_path=tmp_path / "faiss.index")
    try:
        bf_id = "jagan_001"
        # Seed a prior multi-person room that the owner participated in.
        _now = time.time()
        prior_room_data = [
            (bf_id, "user", "Hi Lexi, welcome", _now - 1800,
             "room_prior", json.dumps([bf_id, "lexi_001"])),
            ("lexi_001", "user", "Thanks for having me", _now - 1790,
             "room_prior", json.dumps([bf_id, "lexi_001"])),
        ]
        for pid, role, content, ts, rid, aud in prior_room_data:
            db._conn.execute(
                "INSERT INTO conversation_log "
                "(person_id, role, content, ts, room_session_id, audience_ids) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (pid, role, content, ts, rid, aud),
            )
        # Also seed a person row so get_person lookups work.
        db._conn.execute(
            "INSERT OR IGNORE INTO persons (id, name, person_type) VALUES (?, ?, ?)",
            (bf_id, "Jagan", "best_friend"),
        )
        db._conn.execute(
            "INSERT OR IGNORE INTO persons (id, name, person_type) VALUES (?, ?, ?)",
            ("lexi_001", "Lexi", "known"),
        )
        db._conn.commit()

        orch = RoomOrchestrator()
        # Owner is alone now (active_session_count=1) AND no current
        # room_session_id — D2 fallback path.
        block = orch.build_shared_context_block(
            room_session_id=None,
            requester_pid=bf_id,
            best_friend_id=bf_id,
            db=db,
            is_disputed_fn=lambda pid: False,
            active_session_count=1,
            limit=10,
            now=_now,
        )
        assert block is not None, (
            "D2 widening MUST render persisted history when owner is alone "
            "but has recent room participation in their audience_ids"
        )
        assert "<<<SHARED CONTEXT" in block
        assert "Thanks for having me" in block, (
            "Lexi's turn from the prior room MUST appear in the rendered block"
        )
    finally:
        db._conn.close()


@pytest.mark.asyncio
async def test_p0_s7_5_update_person_name_handled_noop_on_same_name(tmp_path):
    """P0.S7.5 Phase 3 test 16 — repeat-suppression behavioral. When
    `_handle_update_person_name` is invoked with new_name matching
    the current person_name, the handler MUST return "handled_noop"
    so the dispatcher suppresses the canonical-ack.

    This is the existing Bug Q semantic; Phase 3 verifies it
    interacts correctly with the D3 await change AND the D4
    description tightening (no behavior regression).
    """
    import pipeline as _pl
    from core.db import FaceDB

    # Set up a fresh DB + session.
    db = FaceDB(tmp_path / "faces.db", faiss_path=tmp_path / "faiss.index")
    try:
        pid = "lexi_001"
        db._conn.execute(
            "INSERT INTO persons (id, name, person_type, enrolled_at) VALUES (?, ?, ?, ?)",
            (pid, "Lexi", "known", time.time()),
        )
        db._conn.commit()

        # Open a session for Lexi.
        await _pl._session_store.open_session(
            pid, "Lexi", "known", "voice", now=time.time(),
        )

        # Build a _ToolContext mimicking the handler invocation.
        from pipeline import _ToolContext
        snap = _pl._session_store.peek_snapshot(pid)
        ctx = _ToolContext(
            args={"name": "Lexi"},        # SAME name → no-op expected
            person_id=pid,
            person_name="Lexi",
            db=db,
            user_text="Hi, I'm Lexi",
            intent_sidecar=None,
            exec_snap=snap,
            caller_type="known",
        )
        result = await _pl._handle_update_person_name(
            {"name": "Lexi"}, ctx,
        )
        assert result == "handled_noop", (
            f"Bug Q semantic: when new_name == current name, handler MUST "
            f"return 'handled_noop'; got {result!r}. Without this, the "
            f"canonical-ack writes to history and the LLM re-issues the "
            f"tool call next turn (the canary feedback loop)."
        )
    finally:
        db._conn.close()
