"""#5 §5.2 — dict-mediated reconciler-clock provenance guard (the paired-invariant blind-spot closer).

The auto-deriving paired-clock invariant (tests/test_clock_consistency_paired.py) is
STRUCTURALLY BLIND to the reconciler routing read: `persons_in_frame[pid]["last_recognized_at"]`
copied from a PresenceSnapshot into a plain dict and consumed in
`core/reconciler._build_routing_inputs` as `now - info["last_recognized_at"] < FACE_STALE`. No
`peek_*` getter appears in that subtraction (it's a dict-literal value), so the getter-based
invariant cannot follow the clock through the dict. This is the highest-blast-radius clock in the
system (it decides who a turn is attributed to), so the allowlist for the presence fields must NOT
be cleared until this surface is structurally guarded.

RATIFIED mechanism (auditor Q1, 2026-06-02): the pragmatic AST-provenance + behavioral pair — 4
conditions (full dict-flow auto-derivation DEFERRED as future hardening). Together they pin the
read to a single (monotonic) clock by construction:

  1. (AST) `_rc_now` — the value passed as `now=` to `_build_routing_inputs(...)` in pipeline.py —
     is assigned from `time.monotonic()`, not `time.time()`.
  2. (AST) the `persons_in_frame` dict passed to the reconciler (`_rs_pif_view`) sources its
     `last_seen` / `last_recognized_at` from PresenceSnapshot attributes obtained via
     `peek_all_snapshots()` / `peek_snapshot()` — pinning the dict's clock provenance to the
     (monotonic-written) presence store, which is what the getter-based invariant can't follow.
  3. (source) `core/reconciler.py` makes no `time.time()` / `time.monotonic()` call (its existing
     clock-discipline — it consumes the caller's `now`), so `now - info["last_recognized_at"]` is
     single-clock by construction once conditions 1+2 hold.
  4. (behavioral, fail-on-revert) `_build_routing_inputs` driven with a `persons_in_frame` built
     via the REAL PresenceStore write path (monotonic) + a monotonic `now` yields a correct
     in-frame `visible_pids`; reverting `now` to wall (`time.time()`) makes the dict-read
     `≈ +1.78e9`, drops the in-frame face from `visible_pids` (the routing mis-attribution this
     migration fixes), and the test fires.

The conditions route through shared AST helpers so this guard is itself non-vacuous (#123 PI-1 /
#128 D1 discipline). Spec: tests/presence_fabric_clock_migration_spec.md §5.2.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_PIPELINE = _REPO_ROOT / "pipeline.py"
_RECONCILER = _REPO_ROOT / "core" / "reconciler.py"


# ── shared AST helpers (forward conditions route through these) ──────────────────

def _find_build_routing_call(tree: ast.AST) -> ast.Call | None:
    """The call to _build_routing_inputs (imported as `_rc_build` in pipeline.py) — match by
    the callee name OR the `persons_in_frame=`+`now=` kwarg signature so an alias rename can't
    hide it."""
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        name = None
        if isinstance(n.func, ast.Name):
            name = n.func.id
        elif isinstance(n.func, ast.Attribute):
            name = n.func.attr
        kw = {k.arg for k in n.keywords}
        if name in ("_build_routing_inputs", "_rc_build") and "persons_in_frame" in kw and "now" in kw:
            return n
    return None


def _kwarg(call: ast.Call, name: str) -> ast.expr | None:
    for k in call.keywords:
        if k.arg == name:
            return k.value
    return None


def _assignment_value(tree: ast.AST, var_name: str) -> ast.expr | None:
    """The RHS of the LAST `var_name = <expr>` assignment in the module (the routing build is
    the only `_rc_now =` / `_rs_pif_view =` site; LAST is robust to any duplicate)."""
    found: ast.expr | None = None
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name) and t.id == var_name:
                    found = n.value
    return found


def _clock_of_call(node: ast.expr | None) -> str | None:
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name) and node.func.value.id == "time"):
        return {"time": "wall", "monotonic": "mono"}.get(node.func.attr)
    return None


# ── Condition 1 — _rc_now (the routing `now=`) is monotonic ─────────────────────

def test_cond1_rc_now_passed_to_reconciler_is_monotonic():
    """The value passed as `now=` to _build_routing_inputs is assigned from time.monotonic()."""
    tree = ast.parse(_PIPELINE.read_text(encoding="utf-8"))
    call = _find_build_routing_call(tree)
    assert call is not None, "could not find the _build_routing_inputs(persons_in_frame=, now=) call"
    now_arg = _kwarg(call, "now")
    assert isinstance(now_arg, ast.Name), (
        f"reconciler `now=` must be a now-variable (so its clock is auditable); got {ast.dump(now_arg)}"
    )
    rhs = _assignment_value(tree, now_arg.id)
    assert _clock_of_call(rhs) == "mono", (
        f"the reconciler routing clock `{now_arg.id}` must be time.monotonic() (it is consumed "
        f"against monotonic-written presence timestamps in the dict-mediated read); "
        f"got {ast.dump(rhs) if rhs is not None else None}"
    )


# ── Condition 2 — the persons_in_frame dict sources timestamps from PresenceSnapshot ───

def test_cond2_persons_in_frame_dict_sourced_from_presence_snapshots():
    """The dict passed as persons_in_frame is a comprehension over peek_all_snapshots()/
    peek_snapshot() whose last_seen + last_recognized_at values are <snapshot>.<attr> — pinning
    the dict's clock provenance to the (monotonic-written) PresenceStore."""
    tree = ast.parse(_PIPELINE.read_text(encoding="utf-8"))
    call = _find_build_routing_call(tree)
    assert call is not None
    pif_arg = _kwarg(call, "persons_in_frame")
    assert isinstance(pif_arg, ast.Name), (
        f"persons_in_frame must be a named dict var so its provenance is traceable; got {ast.dump(pif_arg)}"
    )
    comp = _assignment_value(tree, pif_arg.id)
    assert isinstance(comp, ast.DictComp), (
        f"{pif_arg.id} must be a dict-comprehension over presence snapshots; got "
        f"{type(comp).__name__ if comp is not None else None}"
    )
    # The iterable is a peek_all_snapshots()/peek_snapshot() call on a *_store receiver.
    iters = [g.iter for g in comp.generators]
    snapshot_sourced = any(
        isinstance(it, ast.Call) and isinstance(it.func, ast.Attribute)
        and it.func.attr in ("peek_all_snapshots", "peek_snapshot")
        for it in iters
    )
    assert snapshot_sourced, (
        f"{pif_arg.id} must iterate peek_all_snapshots()/peek_snapshot() (PresenceSnapshot "
        f"source); iters={[ast.dump(i) for i in iters]}"
    )
    target_names = {
        g.target.id for g in comp.generators if isinstance(g.target, ast.Name)
    }
    # The value dict must source last_seen + last_recognized_at from <snapshot_target>.<attr>.
    assert isinstance(comp.value, ast.Dict), "persons_in_frame value must be a dict literal"
    sourced: dict[str, bool] = {"last_seen": False, "last_recognized_at": False}
    for k, v in zip(comp.value.keys, comp.value.values):
        if (isinstance(k, ast.Constant) and k.value in sourced
                and isinstance(v, ast.Attribute) and v.attr == k.value
                and isinstance(v.value, ast.Name) and v.value.id in target_names):
            sourced[k.value] = True
    assert all(sourced.values()), (
        f"persons_in_frame must source last_seen + last_recognized_at from the snapshot "
        f"comprehension target (not a literal/other clock); sourced={sourced}"
    )


# ── Condition 3 — core/reconciler.py is clock-free ──────────────────────────────

def test_cond3_reconciler_makes_no_clock_call():
    """core/reconciler.py contains no time.time()/time.monotonic() call — it consumes the
    caller's `now`, so the dict-mediated read is single-clock by construction."""
    tree = ast.parse(_RECONCILER.read_text(encoding="utf-8"))
    offenders = [
        f"line {n.lineno}: time.{n.func.attr}()"
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and isinstance(n.func.value, ast.Name) and n.func.value.id == "time"
        and n.func.attr in ("time", "monotonic")
    ]
    assert offenders == [], (
        f"core/reconciler.py must not call a clock (it consumes the caller's `now`): {offenders}"
    )


# ── Condition 4 — behavioral, fail-on-revert ────────────────────────────────────

@pytest.mark.asyncio
async def test_cond4_dict_mediated_read_correct_under_mono_fails_under_wall_revert():
    """Drive _build_routing_inputs with a persons_in_frame built via the REAL PresenceStore
    monotonic write path. A monotonic `now` → the just-recognized face is in-window (visible);
    reverting `now` to wall (the pre-#5 _rc_now bug) → the dict-mediated staleness read goes
    hugely positive → the in-frame face is wrongly dropped from visible_pids (routing
    mis-attribution). The wall branch FAILING to drop the face would mean the guard is vacuous."""
    import time as _time
    from core.presence_store import PresenceStore
    from core.reconciler import _build_routing_inputs

    store = PresenceStore()
    # REAL write path, monotonic clock (the Slice-A presence write).
    await store.upsert_face_recognition("jagan_001", "Jagan", 0.9, _time.monotonic())
    pif = {
        s.person_id: {
            "last_seen": s.last_seen,
            "last_recognized_at": s.last_recognized_at,
            "name": s.name,
            "conf": s.conf,
            "source": s.source,
        }
        for s in store.peek_all_snapshots()
    }

    def _visible(now: float) -> tuple:
        _, presence, _ = _build_routing_inputs(
            v_pid=None, v_score=0.0, n_diarize_segments=1, utterance_duration=2.0,
            persons_in_frame=pif, unrecognized_tracks={}, cur_pid="jagan_001",
            cur_person_type="best_friend", n_active_sessions=1,
            voice_gallery_sizes={"jagan_001": 20}, now=now,
        )
        return presence.visible_pids

    # Correct: monotonic now (matches the monotonic presence write).
    assert "jagan_001" in _visible(_time.monotonic()), (
        "with a monotonic now matching the monotonic presence write, the just-recognized face "
        "must be within VOICE_ROUTING_FACE_STALE_SECS → visible"
    )
    # Fail-on-revert: wall now vs the monotonic-written last_recognized_at.
    assert "jagan_001" not in _visible(_time.time()), (
        "fail-on-revert: a wall `now` against the monotonic-written presence timestamp makes the "
        "dict-mediated staleness read ≈ +1.78e9 → the in-frame face is wrongly excluded from "
        "visible_pids (the routing mis-attribution #5 Slice A fixes). If this no longer holds, "
        "the wall/mono divergence stopped mis-routing and this guard is vacuous."
    )
