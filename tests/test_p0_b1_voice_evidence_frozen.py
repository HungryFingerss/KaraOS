"""tests/test_p0_b1_voice_evidence_frozen.py — P0.B1 D1 invariants.

`VoiceEvidence` is now ``@dataclass(frozen=True, slots=True)``. Every
field update REBINDS the parent ``Session.evidence`` field via
``dataclasses.replace()`` — direct attribute assignment raises
``dataclasses.FrozenInstanceError`` at runtime.

Six anchors live in this file; the 7th anchor
(``test_to_snapshot_copies_voice_evidence``) stays in
``tests/test_session_state_invariants.py:281`` with its seed line
migrated to ``s.evidence = dataclasses.replace(...)`` per Plan v1 §1
Surface 3. Total P0.B1 D1 anchor count: 7.

Spec: tests/p0_b1_reconciler_hygiene_audit.md + _plan_v1.md + _plan_v2.md.

Anchor map (Plan v2 §2.3):
  Anchor 1 — decorator AST (frozen + slots)
  Anchor 2 — replace() round-trip preserves all 9 fields
  Anchor 3 — direct mutation raises FrozenInstanceError
  Anchor 4 — SessionStore mutator → snapshot (parametrized over
             update_face_seen + update_voice_heard)
  Anchor 5 — counter mutations + clamp logic
  Anchor 6 — (LIVES ELSEWHERE — test_session_state_invariants.py:281)
  Anchor 7 — AST forward tripwire (production scope only)
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import ast
import asyncio
import dataclasses
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parent.parent
_SESSION_STATE_PY = _REPO_ROOT / "core" / "session_state.py"


# ─────────────────────────────────────────────────────────────────────────
# Anchor 1 — VoiceEvidence decorator carries frozen=True + slots=True (AST)
# ─────────────────────────────────────────────────────────────────────────


def test_voice_evidence_decorator_is_frozen_and_slotted():
    """D1 Anchor 1 — AST-walk `core/session_state.py` → find `class
    VoiceEvidence` → assert decorator's `frozen=True` AND `slots=True`
    keywords. Forward-property: prevents future regression where someone
    drops one of the flags."""
    tree = ast.parse(_SESSION_STATE_PY.read_text(encoding="utf-8"))
    cls = None
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "VoiceEvidence":
            cls = node
            break
    assert cls is not None, "VoiceEvidence class not found in core/session_state.py"
    assert cls.decorator_list, "VoiceEvidence missing @dataclasses.dataclass decorator"

    # Expect single @dataclasses.dataclass(frozen=True, slots=True) call
    dec = cls.decorator_list[0]
    assert isinstance(dec, ast.Call), (
        "VoiceEvidence decorator must be a Call (e.g. @dataclasses.dataclass(...))"
    )
    kw_names = {kw.arg: kw for kw in dec.keywords}
    assert "frozen" in kw_names, (
        "VoiceEvidence decorator must include `frozen=True` (P0.B1 D1 contract)"
    )
    assert "slots" in kw_names, (
        "VoiceEvidence decorator must include `slots=True` (memory + drift discipline)"
    )
    frozen_val = kw_names["frozen"].value
    slots_val = kw_names["slots"].value
    assert isinstance(frozen_val, ast.Constant) and frozen_val.value is True, (
        f"VoiceEvidence `frozen` must be the literal True (got {ast.dump(frozen_val)})"
    )
    assert isinstance(slots_val, ast.Constant) and slots_val.value is True, (
        f"VoiceEvidence `slots` must be the literal True (got {ast.dump(slots_val)})"
    )


# ─────────────────────────────────────────────────────────────────────────
# Anchor 2 — replace() round-trip preserves all 9 fields
# ─────────────────────────────────────────────────────────────────────────


def test_voice_evidence_replace_round_trip_preserves_all_fields():
    """D1 Anchor 2 — construct VoiceEvidence with all 9 fields set to
    non-default values; `replace()` with one kwarg; assert other 8 fields
    preserved + the one updated. Validates the Plan v1 §3.2 / §4.5 risk
    (replace semantics on slotted+frozen)."""
    from core.session_state import VoiceEvidence
    ev = VoiceEvidence(
        face_match_conf=0.91,
        face_last_seen_ts=100.0,
        anti_spoof_live=True,
        anti_spoof_score=0.88,
        anti_spoof_last_ts=101.0,
        voice_match_conf=0.77,
        voice_sample_count=12,
        voice_last_heard_ts=102.0,
        bootstrap_credits=5,
    )
    ev2 = dataclasses.replace(ev, face_match_conf=0.99)

    # The replaced field updated
    assert ev2.face_match_conf == 0.99
    # All 8 other fields preserved exactly
    assert ev2.face_last_seen_ts == 100.0
    assert ev2.anti_spoof_live is True
    assert ev2.anti_spoof_score == 0.88
    assert ev2.anti_spoof_last_ts == 101.0
    assert ev2.voice_match_conf == 0.77
    assert ev2.voice_sample_count == 12
    assert ev2.voice_last_heard_ts == 102.0
    assert ev2.bootstrap_credits == 5
    # Original instance is unmodified (immutability invariant)
    assert ev.face_match_conf == 0.91
    # The returned instance is a NEW frozen object, not aliased
    assert ev2 is not ev


# ─────────────────────────────────────────────────────────────────────────
# Anchor 3 — direct mutation raises FrozenInstanceError
# ─────────────────────────────────────────────────────────────────────────


def test_voice_evidence_direct_mutation_raises_frozen_error():
    """D1 Anchor 3 — defensive: construct VoiceEvidence; attempt
    ``ev.anti_spoof_live = True``; assert raises an exception consistent
    with frozen+slots semantics (FrozenInstanceError, TypeError, or
    AttributeError — Python 3.13's slotted-frozen dataclass __setattr__
    can raise any of the three depending on the path; the contract is
    'writes blocked', not the specific exception class)."""
    from core.session_state import VoiceEvidence
    ev = VoiceEvidence()
    with pytest.raises((dataclasses.FrozenInstanceError, TypeError, AttributeError)):
        ev.anti_spoof_live = True  # type: ignore[misc]


# ─────────────────────────────────────────────────────────────────────────
# Anchor 4 — SessionStore mutator → snapshot (parametrized)
# ─────────────────────────────────────────────────────────────────────────


_FACE_NOW = 100.0
_VOICE_NOW = 200.0


@pytest.mark.parametrize(
    ("mutator_name", "kwargs", "expected_evidence_updates", "expected_session_updates"),
    [
        (
            "update_face_seen",
            {"conf": 0.95, "ts": _FACE_NOW, "anti_spoof_live": True, "anti_spoof_score": 0.85},
            {
                "face_match_conf": 0.95,
                "face_last_seen_ts": _FACE_NOW,
                "anti_spoof_live": True,
                "anti_spoof_score": 0.85,
                "anti_spoof_last_ts": _FACE_NOW,
            },
            {"last_face_seen": _FACE_NOW},
        ),
        (
            "update_voice_heard",
            {"conf": 0.85, "ts": _VOICE_NOW},
            {
                "voice_match_conf": 0.85,
                "voice_last_heard_ts": _VOICE_NOW,
            },
            {"last_spoke_at": _VOICE_NOW},
        ),
    ],
    ids=["update_face_seen", "update_voice_heard"],
)
def test_session_store_mutator_propagates_through_snapshot(
    mutator_name, kwargs, expected_evidence_updates, expected_session_updates,
):
    """D1 Anchor 4 — open session via SessionStore; call mutator with
    kwargs; peek snapshot; assert each evidence + session field reflects
    the update. End-to-end integration that the rebinding via
    ``dataclasses.replace()`` survives across the
    mutator→Session→_to_snapshot→snapshot chain."""
    from core.session_state import SessionStore

    async def _run():
        store = SessionStore()
        await store.open_session(
            person_id="p1", person_name="Alice",
            person_type="known", session_type="face",
            now=1.0,
        )
        mutator = getattr(store, mutator_name)
        await mutator("p1", **kwargs)
        snap = store.peek_snapshot("p1")
        assert snap is not None, "snapshot missing after mutator call"
        for field, expected in expected_evidence_updates.items():
            actual = getattr(snap.evidence, field)
            assert actual == expected, (
                f"snap.evidence.{field}: expected {expected!r}, got {actual!r}"
            )
        for field, expected in expected_session_updates.items():
            actual = getattr(snap, field)
            assert actual == expected, (
                f"snap.{field}: expected {expected!r}, got {actual!r}"
            )

    asyncio.run(_run())


# ─────────────────────────────────────────────────────────────────────────
# Anchor 5 — counter mutations + clamp logic
# ─────────────────────────────────────────────────────────────────────────


def test_session_store_counter_mutations_preserve_clamps():
    """D1 Anchor 5 — counter mutations route through `replace()` while
    preserving clamp invariants. Verifies the four counter methods
    (increment_voice_sample_count, decrement_bootstrap_credits with
    max(0, ...) clamp, set_bootstrap_credits, increment_bootstrap_credits
    with min(+1, cap) clamp) all rebind correctly + clamp arithmetic
    survives the migration."""
    from core.session_state import SessionStore

    async def _run():
        store = SessionStore()
        await store.open_session(
            person_id="p1", person_name="Alice",
            person_type="known", session_type="face",
            now=1.0, bootstrap_credits=5, voice_sample_count=2,
        )

        # Increment voice_sample_count + decrement bootstrap_credits
        await store.increment_voice_sample_count("p1")
        await store.decrement_bootstrap_credits("p1")
        snap = store.peek_snapshot("p1")
        assert snap is not None
        assert snap.evidence.voice_sample_count == 3, (
            f"increment_voice_sample_count: expected 3, got {snap.evidence.voice_sample_count}"
        )
        assert snap.evidence.bootstrap_credits == 4, (
            f"decrement_bootstrap_credits: expected 4, got {snap.evidence.bootstrap_credits}"
        )

        # Clamp test: set to 0, then decrement → must stay at 0 (max(0, -1))
        await store.set_bootstrap_credits("p1", 0)
        await store.decrement_bootstrap_credits("p1")
        snap = store.peek_snapshot("p1")
        assert snap is not None
        assert snap.evidence.bootstrap_credits == 0, (
            f"max(0, -1) clamp broken: expected 0, got {snap.evidence.bootstrap_credits}"
        )

        # Cap test: increment 12 times with cap=10 → must stay at 10 (min(+1, cap))
        for _ in range(12):
            await store.increment_bootstrap_credits("p1", cap=10)
        snap = store.peek_snapshot("p1")
        assert snap is not None
        assert snap.evidence.bootstrap_credits == 10, (
            f"min(+1, cap=10) clamp broken: expected 10, got "
            f"{snap.evidence.bootstrap_credits}"
        )

    asyncio.run(_run())


# ─────────────────────────────────────────────────────────────────────────
# Anchor 7 — AST forward tripwire (production scope only)
# ─────────────────────────────────────────────────────────────────────────


def test_no_direct_voice_evidence_mutation_outside_sessionstore():
    """D1 Anchor 7 — AST-walk `core/session_state.py` ONLY (production
    scope per Plan v2 §3 Q1 lock). Find every assignment target shaped
    like ``<base>.evidence.<field>`` (Attribute targets where the parent
    is itself an Attribute named `evidence`). Assert ZERO such sites
    remain — under frozen=True, all evidence mutation MUST go through
    ``s.evidence = dataclasses.replace(s.evidence, ...)`` rebinding.

    Test files exempt per Plan v2 §3.2 — test fixtures legitimately
    seed via the rebinding pattern; scanning tests would false-positive
    on legitimate seeding code.

    Future-proofing per Plan v2 §3.3: if a future production code path
    OUTSIDE `core/session_state.py` ever needs to mutate VoiceEvidence,
    extending the scan list requires explicit rationale (mirrors P0.S6
    `_REGISTRY_ALLOWLIST` discipline).
    """
    tree = ast.parse(_SESSION_STATE_PY.read_text(encoding="utf-8"))
    violations: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for tgt in targets:
                # Looking for: <base>.evidence.<field> = <value>
                # tgt is ast.Attribute with attr=<field> and value=ast.Attribute(attr="evidence")
                if (
                    isinstance(tgt, ast.Attribute)
                    and isinstance(tgt.value, ast.Attribute)
                    and tgt.value.attr == "evidence"
                ):
                    try:
                        expr_src = ast.unparse(tgt)
                    except Exception:
                        expr_src = f"<...>.evidence.{tgt.attr}"
                    violations.append((tgt.lineno, expr_src))

    assert not violations, (
        f"P0.B1 D1 forward tripwire FAILED — direct VoiceEvidence field "
        f"mutation found in core/session_state.py:\n"
        + "\n".join(f"  line {ln}: {expr}" for ln, expr in violations)
        + "\n\nFix: replace `<base>.evidence.<field> = X` with "
        "`<base>.evidence = dataclasses.replace(<base>.evidence, <field>=X)`."
    )
