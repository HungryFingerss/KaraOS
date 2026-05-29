"""P0.0.7 event_log contract tests (Block E).

15 tests total per Plan v2 R5 breakdown:
  - 12 per-event_type payload-class presence + required-field tests
  - 3 module-level invariants (EVENT_TYPES ↔ payloads, schema_versions
    coverage, natural-pair sanity)

These tests verify the CONTRACT shape of core/event_log/types.py. Structural
invariants (D7 N=1, R1 cache lifetime, R2 round-trip, C1 writer-task-only,
C2 from_json_dict round-trip, C3 dispatch coverage) live in
tests/test_event_log_invariants.py.

Plan: tests/p0_07_plan_v2.md.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import dataclasses
from typing import get_type_hints

import pytest

from core.event_log.types import (
    EVENT_TYPES,
    NATURAL_PARENT_PAIRS,
    SCHEMA_VERSIONS,
    _PAYLOAD_CLASSES,
    AudioInPayload,
    IdentityClaimPayload,
    IntentClassificationPayload,
    MemoryWritePayload,
    PresenceStatePayload,
    RoutingDecisionPayload,
    SessionLifecyclePayload,
    StateWritePayload,
    ToolCallPayload,
    ToolResultPayload,
    TtsOutPayload,
    VisionFramePayload,
)


# Required-field sets per Block A spec (Plan v2). Each list is the minimum
# fields the payload dataclass must define. Adding fields is fine; missing
# any of these is a contract regression.
_REQUIRED_FIELDS: dict[str, tuple[type, tuple[str, ...]]] = {
    "audio_in":              (AudioInPayload, (
        "audio_hash", "speech_secs", "stt_text", "language", "pre_roll_ms",
    )),
    "vision_frame":          (VisionFramePayload, (
        "frame_id", "frame_path", "frame_ts", "n_detections", "recognized",
        "unrecognized_track_ids", "anti_spoof_live", "anti_spoof_score",
    )),
    "identity_claim":        (IdentityClaimPayload, ("claim",)),
    "presence_state":        (PresenceStatePayload, ("presence",)),
    "routing_decision":      (RoutingDecisionPayload, ("decision", "utt_band")),
    "intent_classification": (IntentClassificationPayload, (
        "sidecar", "mode", "text", "from_cache",
    )),
    "tool_call":             (ToolCallPayload, (
        "name", "args", "person_id", "intent_sidecar",
    )),
    "tool_result":           (ToolResultPayload, ("status", "response_text", "error")),
    "memory_write":          (MemoryWritePayload, (
        "person_id", "role", "text", "room_session_id", "audience_ids",
    )),
    "state_write":           (StateWritePayload, (
        "mode", "current_person", "current_person_id", "visible_people", "message",
    )),
    "tts_out":               (TtsOutPayload, (
        "text", "text_full_hash", "language", "was_stream", "purpose",
        "duration_ms_est",
    )),
    "session_lifecycle":     (SessionLifecyclePayload, (
        "lifecycle", "person_id", "person_name", "source", "person_type",
        "room_session_id",
    )),
}


# ══════════════════════════════════════════════════════════════════════════
# Per-event_type contract tests (12)
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("event_type", sorted(_REQUIRED_FIELDS.keys()))
def test_payload_dataclass_present_and_valid(event_type: str):
    """One contract test per event_type — asserts:
      - The payload dataclass exists.
      - All required fields are present.
      - It's a dataclass (decorated correctly).
      - It's frozen (event payloads must not mutate after construction).
    """
    payload_cls, required_fields = _REQUIRED_FIELDS[event_type]

    assert dataclasses.is_dataclass(payload_cls), (
        f"{event_type}: {payload_cls.__name__} is not a dataclass. "
        "Decorate with @dataclass(frozen=True)."
    )

    # Frozen guarantee — payloads must be immutable.
    assert getattr(payload_cls, "__dataclass_params__").frozen, (
        f"{event_type}: {payload_cls.__name__} must be `frozen=True`. "
        "Event payloads should not mutate after construction."
    )

    actual_fields = {f.name for f in dataclasses.fields(payload_cls)}
    missing = set(required_fields) - actual_fields
    assert not missing, (
        f"{event_type}: {payload_cls.__name__} missing required fields "
        f"{sorted(missing)}. Required per Plan v2 Block A: "
        f"{list(required_fields)}."
    )


# ══════════════════════════════════════════════════════════════════════════
# Module-level invariants (3)
# ══════════════════════════════════════════════════════════════════════════


def test_event_types_set_matches_payload_dataclasses():
    """Every type in EVENT_TYPES has a corresponding *Payload dataclass.

    Bidirectional check:
      - Every EVENT_TYPES member has a _REQUIRED_FIELDS row.
      - Every _REQUIRED_FIELDS row's event_type is in EVENT_TYPES.

    Catches the case where a type is added to one set but not the other.
    """
    types_with_required = set(_REQUIRED_FIELDS.keys())
    assert EVENT_TYPES == types_with_required, (
        f"EVENT_TYPES and the required-fields registry diverged.\n"
        f"  In EVENT_TYPES not in registry: {EVENT_TYPES - types_with_required}\n"
        f"  In registry not in EVENT_TYPES: {types_with_required - EVENT_TYPES}\n"
        "Adding an event_type requires updating BOTH this test's "
        "_REQUIRED_FIELDS dict AND types.EVENT_TYPES."
    )


def test_schema_versions_dict_covers_every_event_type():
    """Every type in EVENT_TYPES has a SCHEMA_VERSIONS entry."""
    missing = EVENT_TYPES - set(SCHEMA_VERSIONS.keys())
    assert not missing, (
        f"SCHEMA_VERSIONS missing entries for: {sorted(missing)}. "
        "Add an entry per event_type (start at version 1)."
    )

    extra = set(SCHEMA_VERSIONS.keys()) - EVENT_TYPES
    assert not extra, (
        f"SCHEMA_VERSIONS has entries for unknown event_types: {sorted(extra)}. "
        "Remove stale entries or add the types to EVENT_TYPES."
    )

    # Every version must be a positive int.
    for event_type, version in SCHEMA_VERSIONS.items():
        assert isinstance(version, int) and version >= 1, (
            f"SCHEMA_VERSIONS[{event_type!r}] = {version!r} — must be int >= 1."
        )


def test_natural_parent_pairs_reference_known_types():
    """Every (child, parent) pair in NATURAL_PARENT_PAIRS references
    types that exist in EVENT_TYPES. Prevents typos that would silently
    break parent-resolution at emit time."""
    for child, parent in NATURAL_PARENT_PAIRS:
        assert child in EVENT_TYPES, (
            f"NATURAL_PARENT_PAIRS references unknown child type "
            f"{child!r}. Add to EVENT_TYPES or remove the pair."
        )
        assert parent in EVENT_TYPES, (
            f"NATURAL_PARENT_PAIRS references unknown parent type "
            f"{parent!r}. Add to EVENT_TYPES or remove the pair."
        )
        assert child != parent, (
            f"NATURAL_PARENT_PAIRS: self-loop ({child!r}, {parent!r}). "
            "An event can't be its own parent."
        )
