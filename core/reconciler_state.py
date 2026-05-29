"""Reconciler input/output dataclasses + valid-action set.

Phase 3 of the Voice/Vision Independence refactor. Plain types only —
no business logic, no pipeline imports, no voice/vision channel imports.
The cascade in core/reconciler.py consumes these to make routing decisions.

Design reference: RECONCILER_DESIGN.md, sections 3 + 4.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


VALID_ACTIONS: frozenset[str] = frozenset({
    "current",
    "switch_enrolled",
    "new_stranger",
    "ambiguous",
    "multi_segment_voice_mismatch",
    "single_segment_voice_mismatch",
    "short_utterance_voice_mismatch",
    "short_utterance_skip",
    "no_action",
})


@dataclass(frozen=True)
class SessionState:
    """Per-turn snapshot of session-side context the reconciler needs.

    Built by `_build_routing_inputs()` in pipeline.py before the reconciler
    is called. All fields are caller-supplied — reconciler never reads
    pipeline globals directly. `now` is caller-provided for the same reason
    `PresenceState.frame_ts` is (testability + determinism — no time.time()
    inside the reconciler).

    Fields
    ------
    cur_pid:
        Active session holder, or None if no session is open.
    cur_person_type:
        One of "stranger", "known", "best_friend", "disputed", or "" when
        cur_pid is None. Drives Priority 3 / 3.5 thin-stranger relaxation.
    n_active_sessions:
        Count of currently-open sessions across all persons. Drives
        Priority 0 Tier 2 (S93) and Priority 4 multi/single-segment
        mismatch gates (S118/S120/S121) AND the live-bug rule
        `_p4_pyannote_vouched_stranger` (Q3: == 1 explicit).
    voice_gallery_sizes:
        Per-pid voice profile sample count. Used by
        `_effective_switch_threshold(v_pid, voice_gallery_sizes)` so
        Priority 1's switch threshold scales with the target's profile
        maturity.
    cur_holder_voice_n:
        Convenience: `voice_gallery_sizes.get(cur_pid, 0)`. Drives
        Priority 3.5 bootstrapping-stranger gate AND Priority 4
        single-segment mismatch gate's mature-holder check.
    now:
        Caller-provided wall clock. Reconciler must not call time.time().
    """
    cur_pid:              Optional[str]
    cur_person_type:      str
    n_active_sessions:    int
    voice_gallery_sizes:  dict[str, int]
    cur_holder_voice_n:   int
    now:                  float


@dataclass(frozen=True)
class RoutingDecision:
    """Cascade output. One per cascade rule that matches a turn.

    Fields
    ------
    pid:
        Resolved pid for `switch_enrolled` (the v_pid the cascade is
        switching INTO). None for `new_stranger` (caller mints the pid),
        for hold/drop/ambiguous actions, and for `no_action`.
    action:
        One of the strings in `VALID_ACTIONS`. The per-rule tests pin
        which action each rule returns.
    reasoning:
        Human-readable explanation. Caller logs this on the
        `[Voice] Routing` line for diagnostics.
    rule_fired:
        Machine-readable rule name (e.g. `_p4_pyannote_vouched_stranger`).
        Set by the `reconcile()` dispatcher via `dataclasses.replace`
        after a rule helper returns; rule helpers leave the empty default.
        Used by per-rule tests for strong regression assertions
        (`assert decision.rule_fired == "_pX_..."`) — two rules can return
        the same action, so action alone is insufficient.
    """
    pid:        Optional[str]
    action:     str
    reasoning:  str
    rule_fired: str = ""
