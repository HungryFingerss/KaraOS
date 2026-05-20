"""P0.0.7 Step 7 — Event log replay fixtures.

Hand-authored scenario builders that exercise the FULL ingestion path
(producer hooks + writer-task parent threading + JPEG storage) rather
than synthetic INSERTs. Reusable across:

  - `tests/test_event_log_replay.py` — 5 Step 7 smoke tests.
  - **P0.S1's anti-spoof regression** — replay these chains to validate
    new gates without needing live camera input (D7.4 lock).
  - Future P0.R / P0.S work — any feature that consumes the event_log
    can replay a captured-canary-shaped scenario for regression tests.

Scenarios (D7.1):
  A. `build_greeting_flow`           — clean known-person turn
  B. `build_stranger_first_encounter` — stranger says system name, becomes session
  C. `build_multi_person_room`        — 2 sessions interleaved with shared room_session_id
  D. `build_dispute_path`             — low-confidence claim triggers ambiguous routing + rejected rename

Each scenario:
  - Accepts identifier params (session_id, room_session_id, pids, now) so
    callers can compose multiple scenarios into the same in-memory DB.
  - Returns the assigned event_ids in chronological order so tests can
    walk parent chains.
  - Uses `safe_emit_sync` (the production hook surface) so the natural-pair
    `parent_event_id` resolution + `_recent_parent` cache lifecycle runs
    exactly as it does on a live boot.

Pytest fixture `replay_session_fixture` ships alongside as a convenient
`ReplayContext` wrapper for test-isolation + read-back helpers.

Plan: tests/p0_07_plan_v2.md.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import pytest

from core.event_log import producer as _producer
from core.event_log import safe_emit_sync
from core.event_log.types import (
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
from core.reconciler_state import RoutingDecision
from core.vision_channel import PresenceState
from core.voice_channel import IdentityClaim


# ──────────────────────────────────────────────────────────────────────────
# Pytest fixture + ReplayContext wrapper
# ──────────────────────────────────────────────────────────────────────────


@dataclass
class ReplayContext:
    """Helpers for inspecting events written via the producer during a test."""

    def all_events(self) -> list[dict[str, Any]]:
        return _producer._query_all_events_for_tests()

    def events_of_type(self, event_type: str) -> list[dict[str, Any]]:
        return [e for e in self.all_events() if e["event_type"] == event_type]

    def events_for_session(self, session_id: str) -> list[dict[str, Any]]:
        return [e for e in self.all_events() if e["session_id"] == session_id]

    def find_by_id(self, event_id: int) -> Optional[dict[str, Any]]:
        for e in self.all_events():
            if e["id"] == event_id:
                return e
        return None


@pytest.fixture
def replay_session_fixture(monkeypatch):
    """Foundation fixture: enable EVENT_LOG_TESTING + open in-memory SQLite.

    Yields a `ReplayContext` for assertions. Producer state resets after
    each test so events from prior cases don't leak.
    """
    monkeypatch.setattr(_producer, "EVENT_LOG_TESTING", True)
    monkeypatch.setattr(_producer, "EVENT_LOG_ENABLED", False)
    _producer._reset_for_tests()
    _producer._open_testing_db_sync()
    try:
        yield ReplayContext()
    finally:
        _producer._reset_for_tests()


# ──────────────────────────────────────────────────────────────────────────
# Scenario A — Clean greeting flow (canonical known-person turn)
# ──────────────────────────────────────────────────────────────────────────


def build_greeting_flow(
    *,
    session_id: str = "jagan_001",
    room_session_id: Optional[str] = "room_greet_xyz",
    now: float = 1779008000.0,
) -> list[int]:
    """A. Clean greeting flow — Jagan (best_friend) says "hello" and the
    assistant searches memory + responds.

    Event chain (chronological):
      session_lifecycle=open
        → audio_in
            → identity_claim (parent natural-pair)
                → routing_decision (parent natural-pair)
        → intent_classification
        → tool_call
            → tool_result (parent natural-pair)
        → memory_write × 2 (user + assistant)
        → state_write
        → tts_out
      session_lifecycle=close

    Returns the assigned event_ids in emission order.
    """
    ids: list[int] = []

    ids.append(safe_emit_sync(
        "session_lifecycle",
        SessionLifecyclePayload(
            lifecycle="open", person_id=session_id, person_name="Jagan",
            source="face", person_type="best_friend",
            room_session_id=room_session_id,
        ),
        session_id=session_id, room_session_id=room_session_id,
    ))
    ids.append(safe_emit_sync(
        "audio_in",
        AudioInPayload(
            audio_hash="sha256:" + "a" * 16,
            speech_secs=1.2, stt_text="hello there",
            language="en", pre_roll_ms=200,
        ),
        session_id=session_id, room_session_id=room_session_id,
    ))
    ids.append(safe_emit_sync(
        "identity_claim",
        IdentityClaimPayload(
            claim=IdentityClaim(
                pid=session_id, confidence=0.85, n_diarize_segments=1,
                utterance_duration=1.2, reasoning="strong self-match",
                raw_segment_scores=((session_id, 0.85),),
            ),
        ),
        session_id=session_id, room_session_id=room_session_id,
    ))
    ids.append(safe_emit_sync(
        "routing_decision",
        RoutingDecisionPayload(
            decision=RoutingDecision(
                pid=session_id, action="current",
                reasoning="self-match confirmed",
                rule_fired="_p3_self_match_with_face",
            ),
            utt_band="normal",
        ),
        session_id=session_id, room_session_id=room_session_id,
    ))
    ids.append(safe_emit_sync(
        "intent_classification",
        IntentClassificationPayload(
            sidecar={"turn_intent": "casual_conversation", "confidence": 0.92},
            mode="primary", text="hello there", from_cache=False,
        ),
        session_id=session_id, room_session_id=room_session_id,
    ))
    ids.append(safe_emit_sync(
        "tool_call",
        ToolCallPayload(
            name="search_memory", args={"query": "hello"},
            person_id=session_id, intent_sidecar=None,
        ),
        session_id=session_id, room_session_id=room_session_id,
    ))
    ids.append(safe_emit_sync(
        "tool_result",
        ToolResultPayload(status="handled", response_text="ok", error=None),
        session_id=session_id, room_session_id=room_session_id,
    ))
    ids.append(safe_emit_sync(
        "memory_write",
        MemoryWritePayload(
            person_id=session_id, role="user", text="hello there",
            room_session_id=room_session_id,
            audience_ids=(session_id,),
        ),
        session_id=session_id, room_session_id=room_session_id,
    ))
    ids.append(safe_emit_sync(
        "memory_write",
        MemoryWritePayload(
            person_id=session_id, role="assistant",
            text="Hello Jagan! Good to see you.",
            room_session_id=room_session_id,
            audience_ids=(session_id,),
        ),
        session_id=session_id, room_session_id=room_session_id,
    ))
    ids.append(safe_emit_sync(
        "state_write",
        StateWritePayload(
            mode="watching", current_person="Jagan",
            current_person_id=session_id, visible_people=("Jagan",),
            message="",
        ),
        session_id=session_id,
    ))
    ids.append(safe_emit_sync(
        "tts_out",
        TtsOutPayload(
            text="Hello Jagan! Good to see you.",
            text_full_hash="sha256:" + "b" * 16,
            language="en", was_stream=True,
            purpose="greeting", duration_ms_est=1400,
        ),
        session_id=session_id, room_session_id=room_session_id,
    ))
    ids.append(safe_emit_sync(
        "session_lifecycle",
        SessionLifecyclePayload(
            lifecycle="close", person_id=session_id, person_name="Jagan",
            source="face", person_type="best_friend",
            room_session_id=room_session_id,
        ),
        session_id=session_id, room_session_id=room_session_id,
    ))
    return [i for i in ids if i is not None]


# ──────────────────────────────────────────────────────────────────────────
# Scenario B — Stranger first-encounter
# ──────────────────────────────────────────────────────────────────────────


def build_stranger_first_encounter(
    *,
    session_id: str = "stranger_abc123",
    now: float = 1779009000.0,
) -> list[int]:
    """B. Stranger first-encounter — vision_frame frames detect an unknown
    face; stranger says system name, gate opens, session_lifecycle=open.

    Event chain:
      vision_frame × 3      (anti-spoof live=True, unrecognized track)
      audio_in              (engagement-gate phrase: "Hi, my name is Lexi")
        → identity_claim    (no gallery match yet)
            → routing_decision (action=new_stranger)
      session_lifecycle=open (source=voice, person_type=stranger)
      intent_classification  (turn_intent=assign_own_name)

    Returns assigned event_ids in emission order.
    """
    ids: list[int] = []

    # Vision-loop scan frames before the stranger speaks — load-bearing
    # anti_spoof fields stay True (live face) for the canary replay.
    for i in range(3):
        ids.append(safe_emit_sync(
            "vision_frame",
            VisionFramePayload(
                frame_id=f"frame_b{i:02d}",
                frame_path=f"faces/frames/frame_b{i:02d}.jpg",
                frame_ts=now + i * 0.5,
                n_detections=1,
                recognized=(),
                unrecognized_track_ids=(42,),
                anti_spoof_live=True,
                anti_spoof_score=0.91 + i * 0.01,
            ),
        ))

    # presence_state snapshot after the vision_frame burst — vision_channel
    # observes the scene before the engagement gate fires.
    ids.append(safe_emit_sync(
        "presence_state",
        PresenceStatePayload(
            presence=PresenceState(
                visible_pids=(),
                unrecognized_track_ids=(42,),
                per_pid_confidence={},
                per_pid_quality={},
                frame_ts=now + 1.5,
                reasoning="1 unrecognized track, no gallery matches",
            ),
        ),
    ))

    ids.append(safe_emit_sync(
        "audio_in",
        AudioInPayload(
            audio_hash="sha256:" + "c" * 16,
            speech_secs=2.1, stt_text="Hi, my name is Lexi",
            language="en", pre_roll_ms=300,
        ),
        session_id=None,  # pre-session boundary
    ))
    ids.append(safe_emit_sync(
        "identity_claim",
        IdentityClaimPayload(
            claim=IdentityClaim(
                pid=None, confidence=0.12, n_diarize_segments=1,
                utterance_duration=2.1, reasoning="no gallery match",
                raw_segment_scores=(),
            ),
        ),
        session_id=None,
    ))
    ids.append(safe_emit_sync(
        "routing_decision",
        RoutingDecisionPayload(
            decision=RoutingDecision(
                pid=None, action="new_stranger",
                reasoning="below threshold, opening new session",
                rule_fired="_p4_new_stranger_low_match",
            ),
            utt_band="normal",
        ),
        session_id=None,
    ))
    ids.append(safe_emit_sync(
        "session_lifecycle",
        SessionLifecyclePayload(
            lifecycle="open", person_id=session_id, person_name="visitor",
            source="voice", person_type="stranger",
            room_session_id=None,
        ),
        session_id=session_id,
    ))
    ids.append(safe_emit_sync(
        "intent_classification",
        IntentClassificationPayload(
            sidecar={"turn_intent": "assign_own_name",
                     "confidence": 0.95, "extracted_value": "Lexi"},
            mode="primary", text="Hi, my name is Lexi", from_cache=False,
        ),
        session_id=session_id,
    ))
    return [i for i in ids if i is not None]


# ──────────────────────────────────────────────────────────────────────────
# Scenario C — Multi-person room (interleaved sessions)
# ──────────────────────────────────────────────────────────────────────────


def build_multi_person_room(
    *,
    pids: tuple[str, str] = ("jagan_001", "lexi_002"),
    room_session_id: str = "room_multi_xyz",
    now: float = 1779010000.0,
) -> list[int]:
    """C. Multi-person room — two persons in the same room_session, taking
    turns. Verifies room_session_id threading + per-session parent caches
    don't bleed across speakers.

    Event chain:
      session_lifecycle=open (pid_a)
      session_lifecycle=open (pid_b)
      audio_in (pid_a speaks)
        → identity_claim (pid_a) → routing_decision (pid_a current)
      audio_in (pid_b speaks)
        → identity_claim (pid_b) → routing_decision (pid_b switch_enrolled)
      session_lifecycle=close (pid_a)
      session_lifecycle=close (pid_b)

    Returns assigned event_ids in emission order.
    """
    pid_a, pid_b = pids
    ids: list[int] = []

    for pid, name, ptype in (
        (pid_a, "Jagan", "best_friend"),
        (pid_b, "Lexi", "known"),
    ):
        ids.append(safe_emit_sync(
            "session_lifecycle",
            SessionLifecyclePayload(
                lifecycle="open", person_id=pid, person_name=name,
                source="face", person_type=ptype,
                room_session_id=room_session_id,
            ),
            session_id=pid, room_session_id=room_session_id,
        ))

    # Jagan speaks first
    ids.append(safe_emit_sync(
        "audio_in",
        AudioInPayload(
            audio_hash="sha256:" + "d" * 16,
            speech_secs=1.5, stt_text="Hey Lexi, are you ready?",
            language="en", pre_roll_ms=200,
        ),
        session_id=pid_a, room_session_id=room_session_id,
    ))
    ids.append(safe_emit_sync(
        "identity_claim",
        IdentityClaimPayload(
            claim=IdentityClaim(
                pid=pid_a, confidence=0.87, n_diarize_segments=1,
                utterance_duration=1.5, reasoning="self-match",
                raw_segment_scores=((pid_a, 0.87),),
            ),
        ),
        session_id=pid_a, room_session_id=room_session_id,
    ))
    ids.append(safe_emit_sync(
        "routing_decision",
        RoutingDecisionPayload(
            decision=RoutingDecision(
                pid=pid_a, action="current",
                reasoning="self-match confirmed",
                rule_fired="_p3_self_match_with_face",
            ),
            utt_band="normal",
        ),
        session_id=pid_a, room_session_id=room_session_id,
    ))
    # Lexi speaks — voice-channel switch
    ids.append(safe_emit_sync(
        "audio_in",
        AudioInPayload(
            audio_hash="sha256:" + "e" * 16,
            speech_secs=1.0, stt_text="Yeah, let's go",
            language="en", pre_roll_ms=200,
        ),
        session_id=pid_b, room_session_id=room_session_id,
    ))
    ids.append(safe_emit_sync(
        "identity_claim",
        IdentityClaimPayload(
            claim=IdentityClaim(
                pid=pid_b, confidence=0.78, n_diarize_segments=1,
                utterance_duration=1.0, reasoning="voice-channel match",
                raw_segment_scores=((pid_b, 0.78),),
            ),
        ),
        session_id=pid_b, room_session_id=room_session_id,
    ))
    ids.append(safe_emit_sync(
        "routing_decision",
        RoutingDecisionPayload(
            decision=RoutingDecision(
                pid=pid_b, action="switch_enrolled",
                reasoning="voice confidence above switch threshold",
                rule_fired="_p1_confident_voice_switch",
            ),
            utt_band="normal",
        ),
        session_id=pid_b, room_session_id=room_session_id,
    ))
    # Closes
    for pid, name, ptype in (
        (pid_a, "Jagan", "best_friend"),
        (pid_b, "Lexi", "known"),
    ):
        ids.append(safe_emit_sync(
            "session_lifecycle",
            SessionLifecyclePayload(
                lifecycle="close", person_id=pid, person_name=name,
                source="face", person_type=ptype,
                room_session_id=room_session_id,
            ),
            session_id=pid, room_session_id=room_session_id,
        ))
    return [i for i in ids if i is not None]


# ──────────────────────────────────────────────────────────────────────────
# Scenario D — Dispute path (low-confidence claim + rejected rename)
# ──────────────────────────────────────────────────────────────────────────


def build_dispute_path(
    *,
    session_id: str = "jagan_001",
    now: float = 1779011000.0,
) -> list[int]:
    """D. Dispute path — low-confidence identity_claim triggers an
    ambiguous routing_decision; subsequent update_person_name tool_call
    gets rejected by the user-text gate.

    Note on "dispute" terminology: the routing layer doesn't have a
    `disputed` action (VALID_ACTIONS = {current, switch_enrolled,
    new_stranger, ambiguous, ...}). Disputes manifest as ambiguous
    routing + rejected mutations; this scenario captures that pattern.

    Event chain:
      session_lifecycle=open (existing best_friend session)
      audio_in (user says "actually I'm not Jagan, call me Bob")
        → identity_claim (low conf — voice doesn't match enrolled Jagan)
            → routing_decision (ambiguous, anti-poisoning kicks in)
      intent_classification (turn_intent=assign_own_name, extracted=Bob)
      tool_call (update_person_name, args={name: 'Bob'})
        → tool_result (status=rejected — user-text gate refuses)
      memory_write (the rejected attempt is captured in turn log)
    """
    ids: list[int] = []

    ids.append(safe_emit_sync(
        "session_lifecycle",
        SessionLifecyclePayload(
            lifecycle="open", person_id=session_id, person_name="Jagan",
            source="face", person_type="best_friend",
            room_session_id=None,
        ),
        session_id=session_id,
    ))
    ids.append(safe_emit_sync(
        "audio_in",
        AudioInPayload(
            audio_hash="sha256:" + "f" * 16,
            speech_secs=2.3, stt_text="Actually I'm not Jagan, call me Bob",
            language="en", pre_roll_ms=200,
        ),
        session_id=session_id,
    ))
    ids.append(safe_emit_sync(
        "identity_claim",
        IdentityClaimPayload(
            claim=IdentityClaim(
                pid=session_id, confidence=0.18, n_diarize_segments=1,
                utterance_duration=2.3,
                reasoning="self-match below SELF_MATCH_FLOOR",
                raw_segment_scores=((session_id, 0.18),),
            ),
        ),
        session_id=session_id,
    ))
    ids.append(safe_emit_sync(
        "routing_decision",
        RoutingDecisionPayload(
            decision=RoutingDecision(
                pid=None, action="ambiguous",
                reasoning="self-match below floor — S51 anti-poisoning",
                rule_fired="_p3_self_match_below_floor",
            ),
            utt_band="normal",
        ),
        session_id=session_id,
    ))
    ids.append(safe_emit_sync(
        "intent_classification",
        IntentClassificationPayload(
            sidecar={"turn_intent": "assign_own_name",
                     "confidence": 0.93, "extracted_value": "Bob"},
            mode="primary",
            text="Actually I'm not Jagan, call me Bob",
            from_cache=False,
        ),
        session_id=session_id,
    ))
    ids.append(safe_emit_sync(
        "tool_call",
        ToolCallPayload(
            name="update_person_name",
            args={"person_id": session_id, "name": "Bob"},
            person_id=session_id,
            intent_sidecar={"turn_intent": "assign_own_name",
                            "confidence": 0.93, "extracted_value": "Bob"},
        ),
        session_id=session_id,
    ))
    ids.append(safe_emit_sync(
        "tool_result",
        ToolResultPayload(
            status="rejected",
            response_text=None,
            error="user-text gate refused mid-session rename of best_friend",
        ),
        session_id=session_id,
    ))
    ids.append(safe_emit_sync(
        "memory_write",
        MemoryWritePayload(
            person_id=session_id, role="user",
            text="Actually I'm not Jagan, call me Bob",
            room_session_id=None,
            audience_ids=(session_id,),
        ),
        session_id=session_id,
    ))
    return [i for i in ids if i is not None]


# ──────────────────────────────────────────────────────────────────────────
# Re-exports
# ──────────────────────────────────────────────────────────────────────────


def build_multi_person_assistant_extraction(
    brain_orchestrator: "Any",
    *,
    owner_name: str = "Jagan",
    owner_pid: str = "j_001",
    visitor_name: str = "Lexi",
    visitor_pid: str = "l_002",
    assistant_turn_content: str = (
        "To make cheese cookies, you'll need butter, sugar, eggs, "
        "flour, and cheese — I can try to walk you through a basic "
        "recipe if you'd like."
    ),
    extracted_facts_stub: "Any" = None,
    canned_llm_output: "dict | None" = None,
) -> "dict[str, Any]":
    """P0.S7.2 Plan v2 §6 P4 — chain 5 fixture.

    Seeds κ extraction facts into ``brain_orchestrator.brain_db`` as if
    Session A's multi-person assistant turn had been processed. The LLM
    call is deterministic — the caller supplies either:

      * ``extracted_facts_stub`` — pre-built ``list[Extraction]`` (advanced).
      * ``canned_llm_output``    — dict matching the
        ``_ASSISTANT_ROOM_EXTRACT_SYSTEM`` JSON schema; the fixture runs
        ``_fan_out_to_participants`` to produce the Extractions.
      * Neither — defaults to a cheese-cookies-recipe canned payload
        targeting visitor_name as the addressee.

    Session B is "ready" once Session A's facts persist — the caller mints
    a fresh owner-only session and exercises the cross-session retrieval
    path via ``_make_memory_search_fn``.

    Args:
        brain_orchestrator: a BrainOrchestrator instance whose ``brain_db``
            holds the knowledge table.
        owner_name / owner_pid: best_friend who returns in Session B.
        visitor_name / visitor_pid: visitor present in Session A's room.
        assistant_turn_content: the assistant text (for log fidelity; not
            used directly when LLM output is canned).
        extracted_facts_stub: pre-built Extraction list (overrides everything).
        canned_llm_output: simulates an LLM response; if None and stub is None,
            a default cheese-cookies payload is used.

    Returns:
        ``{
          'session_a_room_session_id': str,    # the room id Session A used
          'extractions_stored':        list[Extraction],
          'session_b_ready':           bool,   # True once persistence completes
        }``
    """
    # Resolve canonical Extraction list.
    if extracted_facts_stub is not None:
        extractions = list(extracted_facts_stub)
    else:
        # Default payload — addressee = visitor; topic = cheese cookies recipe.
        # Targets the exact 2026-05-18 canary scenario from `tests/p0_s7_2_spec.md`.
        payload = canned_llm_output or {
            "topic": "cheese cookies recipe",
            "action_type": "shared_information",
            "primary_subject_name": visitor_name,
            "key_details": "butter, sugar, eggs, flour, and cheese",
        }
        # Import here to avoid circulars at module-load time.
        from core.brain_agent import _fan_out_to_participants
        extractions = _fan_out_to_participants(
            extracted=payload,
            participant_names=[owner_name, visitor_name],
            participant_pids=[owner_pid, visitor_pid],
            disputed_pids=set(),
        )

    # Mint a deterministic room_session_id so the test can correlate the
    # write site with Session A's room.
    session_a_room_id = f"room_session_a_{owner_pid}_{visitor_pid}"

    # Persist each Extraction under the participant-scoped person_id. The
    # store_knowledge contract takes a single person_id arg; we call once
    # per participant slice so the row's person_id matches the fact's
    # subject scope. turn_id=0 is the "synthetic-seed" marker.
    brain_db = brain_orchestrator.brain_db
    for ext in extractions:
        pid_for_row = ext.person_id or owner_pid
        brain_db.store_knowledge(
            extractions=[ext],
            turn_id=0,
            person_id=pid_for_row,
            agent="p0_s7_2_chain5_seed",
        )

    return {
        "session_a_room_session_id": session_a_room_id,
        "extractions_stored":        extractions,
        "session_b_ready":           True,
    }


__all__ = [
    "ReplayContext",
    "replay_session_fixture",
    "build_greeting_flow",
    "build_stranger_first_encounter",
    "build_multi_person_room",
    "build_dispute_path",
    "build_multi_person_assistant_extraction",
]
