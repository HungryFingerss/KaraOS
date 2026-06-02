"""Canary #2 clock spec — done-field behavioral coverage (#2-#6 / #4).

The migrated DEADLINE-MATH fields fall into two structural classes for verification:

  STORE-GETTER-MEDIATED (consistency invariant covers): fields whose reads go through a
  `peek_*` getter on a store global AND whose writes go through a per-person entry-object
  attribute (`s.attr = param`) or a direct store-attr. The auto-deriving paired-clock
  invariant (test_clock_consistency_paired.py) is the fail-on-revert guard for these.

  DICT-MEDIATED (consistency invariant is BLIND): `last_greeted` + `last_self_update` are
  stored as `self._last_greeted[pid] = ts` (a `Subscript` target, not an `Attribute`), so
  the invariant's setter scan never sees their write clock. For these, the WRITE-CLOCK AST
  GUARD below (Part A) is the ONLY structural fail-on-revert guard — it scans the actual
  call sites in pipeline.py and fails if any clock-spec setter is fed `time.time()`.

KAIROS (#4) reads its clock inside `_kairos_tick`, which IS invocable, so its genuine
fail-on-revert behavioral coverage lives in tests/test_p0_s7_3_kairos_baseline.py +
test_pipeline.py (those seed monotonic values and invoke `_kairos_tick`; reverting the read
clock to `time.time()` makes silence_elapsed go hugely negative and KAIROS stops firing).
This file does NOT duplicate that; it covers greeted/self_update/cloud_failed_at, whose
reads are buried in `_background_vision_loop`/`run`/`conversation_turn`/`_cloud_retry_loop`
(not cleanly invocable) — so they get the AST write-clock guard (Part A, fail-on-revert)
plus runtime gate-logic correctness proofs against the REAL production stores (Part B).
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import ast
import time
from pathlib import Path

import pytest

import core.config as cfg
from core.conversation_store import ConversationStore
from core.pipeline_state_store import PipelineStateStore

REPO_ROOT = Path(__file__).resolve().parent.parent
_PIPELINE = REPO_ROOT / "pipeline.py"


# ─────────────────────────────────────────────────────────────────────────────
# Part A — WRITE-CLOCK AST GUARD (genuine fail-on-revert, line-ref-drift-immune)
# ─────────────────────────────────────────────────────────────────────────────

# Clock-spec setter calls: the timestamp arg MUST be time.monotonic(), never time.time().
# These are the Direction-B WRITE sites for the done fields. For the dict-mediated
# greeted/self_update this is the ONLY structural revert-guard (the paired-clock invariant
# is blind to their Subscript stores).
_CLOCK_SETTER_NAMES = frozenset({
    "touch_greeted",          # ConversationStore — dict-mediated (#2)
    "touch_self_update",      # ConversationStore — dict-mediated (#3)
    "set_last_user_speech_at",  # PipelineStateStore — KAIROS (#4)
    "set_last_kairos_at",       # PipelineStateStore — KAIROS (#4) [reset calls use 0.0; skipped]
})

# Direct module-global / local assigns that feed a monotonic timestamp into a deadline.
_CLOCK_DIRECT_VARS = frozenset({
    "_ct_failed_at",   # cloud_failed_at source, passed to transition_to_sick(failed_at=) (#5)
    "_yolo_last_ran",  # YOLO cadence deadline (#6)
})


def _clock_of(node: ast.AST) -> str | None:
    """'wall' for time.time(), 'mono' for time.monotonic(), else None (not a bare clock)."""
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "time"
        and not node.args
        and not node.keywords
    ):
        return {"time": "wall", "monotonic": "mono"}.get(node.func.attr)
    return None


def _collect_clock_writes(tree: ast.AST) -> list[tuple[str, int, str]]:
    """Return (site_label, lineno, clock) for every clock-spec write whose value is a
    bare time.time()/time.monotonic() call. Non-clock args (e.g. set_last_kairos_at(0.0),
    variable-hop args) are skipped — we only assert on sites that literally pick a clock."""
    out: list[tuple[str, int, str]] = []
    for node in ast.walk(tree):
        # Setter calls: assert the last positional arg's clock.
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _CLOCK_SETTER_NAMES
            and node.args
        ):
            ck = _clock_of(node.args[-1])
            if ck is not None:
                out.append((f"{node.func.attr}()", node.lineno, ck))
        # Direct assigns to the known monotonic source vars.
        elif isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id in _CLOCK_DIRECT_VARS:
                    ck = _clock_of(node.value)
                    if ck is not None:
                        out.append((f"{tgt.id} =", node.lineno, ck))
    return out


def test_done_field_write_sites_use_monotonic() -> None:
    """HARD GATE — every clock-spec done-field WRITE site in pipeline.py uses
    time.monotonic(), never time.time(). This is the fail-on-revert guard for the
    dict-mediated greeted/self_update fields (which the paired-clock invariant cannot see)
    AND a defense-in-depth guard for the KAIROS/cloud/yolo write sites."""
    tree = ast.parse(_PIPELINE.read_text(encoding="utf-8"))
    writes = _collect_clock_writes(tree)
    assert writes, (
        "No clock-spec write sites found in pipeline.py — the AST scan is mis-keyed "
        "(setter renamed? var renamed?). Re-derive _CLOCK_SETTER_NAMES / _CLOCK_DIRECT_VARS."
    )
    reverted = [(label, ln) for (label, ln, ck) in writes if ck == "wall"]
    assert not reverted, (
        "Canary #2 clock-spec WRITE reverted to time.time() (Direction-B mismatch — would "
        "produce wall-write vs monotonic-read elapsed-math on a deadline):\n"
        + "\n".join(f"  pipeline.py:{ln}  {label}  ← time.time()" for label, ln in reverted)
    )


def test_write_clock_guard_covers_dict_mediated_fields() -> None:
    """Meta-guard: the scan actually reaches the dict-mediated touch_greeted +
    touch_self_update sites (the fields the paired-clock invariant is blind to). If a
    future refactor renames those setters, this fails loudly rather than silently dropping
    the only structural coverage those fields have."""
    tree = ast.parse(_PIPELINE.read_text(encoding="utf-8"))
    labels = {label for (label, _, _) in _collect_clock_writes(tree)}
    assert "touch_greeted()" in labels, "greeted (#2) write site no longer scanned"
    assert "touch_self_update()" in labels, "self_update (#3) write site no longer scanned"


# ─────────────────────────────────────────────────────────────────────────────
# Part B — RUNTIME GATE-LOGIC correctness proofs (real production stores + constants)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_greeted_regreet_gate_opens_after_cooldown() -> None:
    """#2 — re-greet gate (`now - peek_last_greeted >= GREET_COOLDOWN`) opens once the
    cooldown has elapsed and stays shut just after a greet, with monotonic-consistent
    write+read. Pre-fix (wall write, monotonic read) the elapsed went hugely negative and
    the gate NEVER opened (the live bug this migration fixed)."""
    store = ConversationStore()
    pid = "greet_p1"

    # Greeted long ago (just over the cooldown) — re-greet must be allowed.
    await store.touch_greeted(pid, time.monotonic() - cfg.GREET_COOLDOWN - 5.0)
    elapsed = time.monotonic() - store.peek_last_greeted(pid)
    assert elapsed >= cfg.GREET_COOLDOWN, (
        f"re-greet gate stuck shut: elapsed={elapsed:.1f}s < GREET_COOLDOWN="
        f"{cfg.GREET_COOLDOWN}s despite greeting {cfg.GREET_COOLDOWN + 5}s ago"
    )

    # Just greeted — cooldown must still be active.
    await store.touch_greeted(pid, time.monotonic())
    assert (time.monotonic() - store.peek_last_greeted(pid)) < cfg.GREET_COOLDOWN, (
        "cooldown should be active immediately after a greet"
    )


@pytest.mark.asyncio
async def test_self_update_cooldown_gate_opens_after_cooldown() -> None:
    """#3 — gallery self-update gate (`now - peek_last_self_update >= SELF_UPDATE_COOLDOWN`)
    behaves sanely with monotonic-consistent write+read."""
    store = ConversationStore()
    pid = "su_p1"

    await store.touch_self_update(pid, time.monotonic() - cfg.SELF_UPDATE_COOLDOWN - 2.0)
    elapsed = time.monotonic() - store.peek_last_self_update(pid)
    assert elapsed >= cfg.SELF_UPDATE_COOLDOWN, (
        f"self-update gate stuck shut: elapsed={elapsed:.1f}s < SELF_UPDATE_COOLDOWN="
        f"{cfg.SELF_UPDATE_COOLDOWN}s"
    )

    await store.touch_self_update(pid, time.monotonic())
    assert (time.monotonic() - store.peek_last_self_update(pid)) < cfg.SELF_UPDATE_COOLDOWN


@pytest.mark.asyncio
async def test_cloud_offline_timeout_gate_fires_after_timeout() -> None:
    """#5 — SICK→OFFLINE timeout (`now - peek_cloud_failed_at >= CLOUD_OFFLINE_TIMEOUT`)
    fires after the timeout with monotonic-consistent write (transition_to_sick) + read."""
    store = PipelineStateStore()

    # Failed long enough ago that the offline timeout has elapsed.
    await store.transition_to_sick(time.monotonic() - cfg.CLOUD_OFFLINE_TIMEOUT - 3.0)
    elapsed = time.monotonic() - store.peek_cloud_failed_at()
    assert elapsed >= cfg.CLOUD_OFFLINE_TIMEOUT, (
        f"SICK→OFFLINE never fires: elapsed={elapsed:.1f}s < CLOUD_OFFLINE_TIMEOUT="
        f"{cfg.CLOUD_OFFLINE_TIMEOUT}s despite failing {cfg.CLOUD_OFFLINE_TIMEOUT + 3}s ago"
    )

    # Just failed — still within the offline grace window.
    await store.transition_to_sick(time.monotonic())
    assert (time.monotonic() - store.peek_cloud_failed_at()) < cfg.CLOUD_OFFLINE_TIMEOUT
