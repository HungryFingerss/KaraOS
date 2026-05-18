"""P0.0.7 event log — closed event-type set, payload dataclasses,
natural-pair causality, schema versioning + dispatch table.

Single authoritative module for the event_log type contract. Producer's
`emit()` consumes these dataclasses; replay reconstructs them via
`from_json_dict` (C2) dispatched on `(event_type, schema_version)` via
`_PAYLOAD_CLASSES` (C3).

Adding a new event_type requires (per D3 + D7 invariants):
  1. Add to EVENT_TYPES (this set).
  2. Add the *Payload dataclass below with `from_json_dict` classmethod.
  3. Add the SCHEMA_VERSIONS entry.
  4. Add the _PAYLOAD_CLASSES entry mapping (event_type, version) → class.
  5. Add the producer hook (one location — D7 N=1 lock).
  6. Update tests/test_event_log_producer_coverage.py (one test per hook).
  7. Update tests/p0_07_event_boundary_audit.md Deliverable 1 table.

Plan: tests/p0_07_plan_v2.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional

from core.reconciler_state import RoutingDecision
from core.vision_channel import PresenceState
from core.voice_channel import IdentityClaim


# ──────────────────────────────────────────────────────────────────────────
# Closed event-type set (D3)
# ──────────────────────────────────────────────────────────────────────────

EVENT_TYPES: frozenset[str] = frozenset({
    "audio_in",
    "vision_frame",
    "identity_claim",
    "presence_state",
    "routing_decision",
    "intent_classification",
    "tool_call",
    "tool_result",
    "memory_write",
    "state_write",
    "tts_out",
    "session_lifecycle",
})


# ──────────────────────────────────────────────────────────────────────────
# Natural-pair causality (D4 + R4 scope rationale)
# ──────────────────────────────────────────────────────────────────────────
#
# (child_event_type, parent_event_type) — when emitting `child`, the
# producer's writer task (C1: writer-task scope only) looks up the most
# recent `parent` for the same session via `_recent_parent` and threads
# its assigned id through as parent_event_id.
#
# v1 scope is intentionally conservative — only the strongest causal
# links that v1's replay use cases require:
#   - tool_call → tool_result          : verify tool-execution shape
#   - audio_in → identity_claim         : trace voice ID back to source audio
#   - identity_claim → routing_decision : trace dispatch back to claim
#
# Deferred candidates (add when replay analysis surfaces concrete need):
#   - intent_classification → audio_in     (classifier input correlation)
#   - memory_write → routing_decision      (turn → log entry causality)
#   - tts_out → routing_decision           (response → routing causality)
#
# Same shape as P0.10's "validation window catches gaps post-ship"
# framing — add edges when the replay tool surfaces them as load-bearing.

NATURAL_PARENT_PAIRS: frozenset[tuple[str, str]] = frozenset({
    ("tool_result", "tool_call"),
    ("identity_claim", "audio_in"),
    ("routing_decision", "identity_claim"),
})


# ──────────────────────────────────────────────────────────────────────────
# Common envelope (D4 docstring locked)
# ──────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class EventEnvelope:
    """Identity fields carried by every event in the log.

    `parent_event_id` is the IMMEDIATE UPSTREAM event in the natural-pair
    chain — NOT a full causal ancestor. Replay reconstruction queries all
    events within `session_id`, not just walks `parent_event_id`
    recursively. See `NATURAL_PARENT_PAIRS` in this module for the
    enumerated set of (child_event_type, parent_event_type) pairs where
    parent_event_id is populated. For all other event types it is None
    and (ts, session_id, room_session_id) drive ordering.
    """
    ts:              float
    session_id:      Optional[str]
    room_session_id: Optional[str]
    event_type:      str
    schema_version:  int
    parent_event_id: Optional[int]


# ──────────────────────────────────────────────────────────────────────────
# Helpers — deserialization plumbing for nested existing dataclasses
# ──────────────────────────────────────────────────────────────────────────


def _identity_claim_from_dict(d: dict[str, Any]) -> IdentityClaim:
    """Reconstruct the existing IdentityClaim dataclass from a JSON dict.

    `raw_segment_scores` serializes as a list of [pid, score] lists; rebuild
    as a tuple of (pid, score) tuples for shape fidelity.
    """
    raw = d.get("raw_segment_scores", ())
    raw_tuples: tuple[tuple[Optional[str], float], ...] = tuple(
        (item[0], float(item[1])) for item in (raw or ())
    )
    return IdentityClaim(
        pid=d.get("pid"),
        confidence=float(d["confidence"]),
        n_diarize_segments=int(d["n_diarize_segments"]),
        utterance_duration=float(d["utterance_duration"]),
        reasoning=d.get("reasoning", ""),
        raw_segment_scores=raw_tuples,
    )


def _presence_state_from_dict(d: dict[str, Any]) -> PresenceState:
    """Reconstruct PresenceState from a JSON dict. Tuples land as lists;
    rebuild as tuples for type fidelity."""
    return PresenceState(
        visible_pids=tuple(d.get("visible_pids", ())),
        unrecognized_track_ids=tuple(d.get("unrecognized_track_ids", ())),
        per_pid_confidence=dict(d.get("per_pid_confidence", {})),
        per_pid_quality=dict(d.get("per_pid_quality", {})),
        frame_ts=float(d.get("frame_ts", 0.0)),
        reasoning=d.get("reasoning", ""),
    )


def _routing_decision_from_dict(d: dict[str, Any]) -> RoutingDecision:
    return RoutingDecision(
        pid=d.get("pid"),
        action=d["action"],
        reasoning=d.get("reasoning", ""),
        rule_fired=d.get("rule_fired", ""),
    )


# ──────────────────────────────────────────────────────────────────────────
# Per-event payload dataclasses
# ──────────────────────────────────────────────────────────────────────────
#
# Every payload has `from_json_dict(cls, d, schema_version=1) -> Self`
# (C2) — replay's inverse of `_event_log_default`. Schema-version-aware
# dispatch lets v2+ branch within the same method.


@dataclass(frozen=True)
class AudioInPayload:
    """audio_in: STT output + acoustic context. Buffer bytes are NOT
    embedded — `audio_hash` correlates to optional sidecar WAV files."""
    audio_hash:   str
    speech_secs:  float
    stt_text:     str
    language:     str
    pre_roll_ms:  int

    @classmethod
    def from_json_dict(cls, d: dict[str, Any], schema_version: int = 1) -> "AudioInPayload":
        return cls(
            audio_hash=d["audio_hash"],
            speech_secs=float(d["speech_secs"]),
            stt_text=d["stt_text"],
            language=d["language"],
            pre_roll_ms=int(d["pre_roll_ms"]),
        )


@dataclass(frozen=True)
class VisionFramePayload:
    """vision_frame: per-frame snapshot from the background scan.

    **P0.S1 prerequisite (locked):** `anti_spoof_live` + `anti_spoof_score`
    are LOAD-BEARING for P0.S1's anti-spoof-on-every-match regression
    test. Removing or making these fields optional in a future refactor
    breaks P0.S1's test surface.

    **D2 lock (no inline images):** `frame_path` references
    `faces/frames/<frame_id>.jpg`. Payload NEVER embeds image bytes.
    """
    frame_id:                 str
    frame_path:               Optional[str]
    frame_ts:                 float
    n_detections:             int
    recognized:               tuple[tuple[str, float, float], ...]
    unrecognized_track_ids:   tuple[int, ...]
    anti_spoof_live:          bool
    anti_spoof_score:         Optional[float]

    @classmethod
    def from_json_dict(cls, d: dict[str, Any], schema_version: int = 1) -> "VisionFramePayload":
        recognized_raw = d.get("recognized", ())
        recognized = tuple(
            (item[0], float(item[1]), float(item[2])) for item in (recognized_raw or ())
        )
        return cls(
            frame_id=d["frame_id"],
            frame_path=d.get("frame_path"),
            frame_ts=float(d["frame_ts"]),
            n_detections=int(d["n_detections"]),
            recognized=recognized,
            unrecognized_track_ids=tuple(int(x) for x in d.get("unrecognized_track_ids", ())),
            anti_spoof_live=bool(d["anti_spoof_live"]),
            anti_spoof_score=(float(d["anti_spoof_score"])
                              if d.get("anti_spoof_score") is not None else None),
        )


@dataclass(frozen=True)
class IdentityClaimPayload:
    """identity_claim: wraps the existing core.voice_channel.IdentityClaim."""
    claim: IdentityClaim

    @classmethod
    def from_json_dict(cls, d: dict[str, Any], schema_version: int = 1) -> "IdentityClaimPayload":
        return cls(claim=_identity_claim_from_dict(d["claim"]))


@dataclass(frozen=True)
class PresenceStatePayload:
    """presence_state: wraps the existing core.vision_channel.PresenceState."""
    presence: PresenceState

    @classmethod
    def from_json_dict(cls, d: dict[str, Any], schema_version: int = 1) -> "PresenceStatePayload":
        return cls(presence=_presence_state_from_dict(d["presence"]))


@dataclass(frozen=True)
class RoutingDecisionPayload:
    """routing_decision: reconciler output + utt_band tag (Block C of P0.10)."""
    decision: RoutingDecision
    utt_band: str

    @classmethod
    def from_json_dict(cls, d: dict[str, Any], schema_version: int = 1) -> "RoutingDecisionPayload":
        return cls(
            decision=_routing_decision_from_dict(d["decision"]),
            utt_band=d["utt_band"],
        )


@dataclass(frozen=True)
class IntentClassificationPayload:
    """intent_classification: classifier sidecar + mode tag."""
    sidecar:    dict[str, Any]
    mode:       str
    text:       str
    from_cache: bool

    @classmethod
    def from_json_dict(cls, d: dict[str, Any], schema_version: int = 1) -> "IntentClassificationPayload":
        return cls(
            sidecar=dict(d.get("sidecar") or {}),
            mode=d["mode"],
            text=d["text"],
            from_cache=bool(d["from_cache"]),
        )


@dataclass(frozen=True)
class ToolCallPayload:
    name:           str
    args:           dict[str, Any]
    person_id:      str
    intent_sidecar: Optional[dict[str, Any]]

    @classmethod
    def from_json_dict(cls, d: dict[str, Any], schema_version: int = 1) -> "ToolCallPayload":
        return cls(
            name=d["name"],
            args=dict(d.get("args") or {}),
            person_id=d["person_id"],
            intent_sidecar=dict(d["intent_sidecar"]) if d.get("intent_sidecar") else None,
        )


@dataclass(frozen=True)
class ToolResultPayload:
    """tool_result: parent_event_id links to the tool_call (natural pair)."""
    status:        str
    response_text: Optional[str]
    error:         Optional[str]

    @classmethod
    def from_json_dict(cls, d: dict[str, Any], schema_version: int = 1) -> "ToolResultPayload":
        return cls(
            status=d["status"],
            response_text=d.get("response_text"),
            error=d.get("error"),
        )


@dataclass(frozen=True)
class MemoryWritePayload:
    person_id:       str
    role:            str
    text:            str
    room_session_id: Optional[str]
    audience_ids:    Optional[tuple[str, ...]]

    @classmethod
    def from_json_dict(cls, d: dict[str, Any], schema_version: int = 1) -> "MemoryWritePayload":
        ids = d.get("audience_ids")
        return cls(
            person_id=d["person_id"],
            role=d["role"],
            text=d["text"],
            room_session_id=d.get("room_session_id"),
            audience_ids=tuple(ids) if ids is not None else None,
        )


@dataclass(frozen=True)
class StateWritePayload:
    """state_write: snapshot of changed fields per state.write call."""
    mode:              str
    current_person:    Optional[str]
    current_person_id: Optional[str]
    visible_people:    tuple[str, ...]
    message:           str

    @classmethod
    def from_json_dict(cls, d: dict[str, Any], schema_version: int = 1) -> "StateWritePayload":
        return cls(
            mode=d["mode"],
            current_person=d.get("current_person"),
            current_person_id=d.get("current_person_id"),
            visible_people=tuple(d.get("visible_people") or ()),
            message=d.get("message", ""),
        )


@dataclass(frozen=True)
class TtsOutPayload:
    """tts_out: text truncated to 500 chars + sha256 of full text."""
    text:            str
    text_full_hash:  str
    language:        str
    was_stream:      bool
    purpose:         str
    duration_ms_est: Optional[int]

    @classmethod
    def from_json_dict(cls, d: dict[str, Any], schema_version: int = 1) -> "TtsOutPayload":
        return cls(
            text=d["text"],
            text_full_hash=d["text_full_hash"],
            language=d["language"],
            was_stream=bool(d["was_stream"]),
            purpose=d["purpose"],
            duration_ms_est=(int(d["duration_ms_est"])
                             if d.get("duration_ms_est") is not None else None),
        )


@dataclass(frozen=True)
class SessionLifecyclePayload:
    lifecycle:       str   # "open" / "close"
    person_id:       str
    person_name:     Optional[str]
    source:          str
    person_type:     str
    room_session_id: Optional[str]

    @classmethod
    def from_json_dict(cls, d: dict[str, Any], schema_version: int = 1) -> "SessionLifecyclePayload":
        return cls(
            lifecycle=d["lifecycle"],
            person_id=d["person_id"],
            person_name=d.get("person_name"),
            source=d["source"],
            person_type=d["person_type"],
            room_session_id=d.get("room_session_id"),
        )


# ──────────────────────────────────────────────────────────────────────────
# Schema versioning (D6) + dispatch table (C3)
# ──────────────────────────────────────────────────────────────────────────


SCHEMA_VERSIONS: dict[str, int] = {
    "audio_in":               1,
    "vision_frame":           1,
    "identity_claim":         1,
    "presence_state":         1,
    "routing_decision":       1,
    "intent_classification":  1,
    "tool_call":              1,
    "tool_result":            1,
    "memory_write":           1,
    "state_write":            1,
    "tts_out":                1,
    "session_lifecycle":      1,
}


# C3: explicit dispatch table for replay deserialization.
# Replay tool reads (event_type, schema_version) from the row and looks up the
# payload class here, then calls cls.from_json_dict(payload_dict).
# Future v2+ schema bumps land as additive entries:
#   ("audio_in", 2): AudioInPayloadV2,
_PAYLOAD_CLASSES: dict[tuple[str, int], type] = {
    ("audio_in",               1): AudioInPayload,
    ("vision_frame",           1): VisionFramePayload,
    ("identity_claim",         1): IdentityClaimPayload,
    ("presence_state",         1): PresenceStatePayload,
    ("routing_decision",       1): RoutingDecisionPayload,
    ("intent_classification",  1): IntentClassificationPayload,
    ("tool_call",              1): ToolCallPayload,
    ("tool_result",            1): ToolResultPayload,
    ("memory_write",           1): MemoryWritePayload,
    ("state_write",            1): StateWritePayload,
    ("tts_out",                1): TtsOutPayload,
    ("session_lifecycle",      1): SessionLifecyclePayload,
}


__all__ = [
    "EVENT_TYPES",
    "NATURAL_PARENT_PAIRS",
    "SCHEMA_VERSIONS",
    "_PAYLOAD_CLASSES",
    "EventEnvelope",
    "AudioInPayload",
    "VisionFramePayload",
    "IdentityClaimPayload",
    "PresenceStatePayload",
    "RoutingDecisionPayload",
    "IntentClassificationPayload",
    "ToolCallPayload",
    "ToolResultPayload",
    "MemoryWritePayload",
    "StateWritePayload",
    "TtsOutPayload",
    "SessionLifecyclePayload",
]
