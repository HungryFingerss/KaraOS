"""P0.0.7 event log + replay harness.

Public surface re-exported here so callers do
`from core.event_log import emit, ...` rather than reaching into the
sub-modules. Internal helpers (`_recent_parent`, `_event_log_default`,
producer writer-task internals) stay private to `producer.py`.

Plan: tests/p0_07_plan_v2.md.
Phase 0 audit: tests/p0_07_event_boundary_audit.md.
"""
from __future__ import annotations

from core.event_log.producer import (
    emit,
    emit_sync,
    safe_emit_sync,
    get_drop_count,
    get_safe_emit_failure_count,
    start_writer,
    stop_writer,
)
from core.event_log.types import (
    EVENT_TYPES,
    NATURAL_PARENT_PAIRS,
    SCHEMA_VERSIONS,
    _PAYLOAD_CLASSES,
    AudioInPayload,
    EventEnvelope,
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
    "emit",
    "emit_sync",
    "safe_emit_sync",
    "get_drop_count",
    "get_safe_emit_failure_count",
    "start_writer",
    "stop_writer",
]
