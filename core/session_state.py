"""
core/session_state.py — P0.7.1: Typed session state foundation.

Design invariants:
- SessionStore has NO sync mutator methods (only peek_snapshot() and __init__).
- All mutations are async (protected by self._lock).
- All reads return SessionSnapshot (frozen + slots) — never the mutable Session.
- peek_snapshot() is sync-safe under single-threaded asyncio + no-sync-mutators
  + frozen-snapshot assumptions.
"""
from __future__ import annotations

import asyncio
import dataclasses
from typing import Optional


@dataclasses.dataclass(slots=True)
class VoiceEvidence:
    face_match_conf:     float = 0.0
    face_last_seen_ts:   float = 0.0
    anti_spoof_live:     bool  = False
    anti_spoof_score:    float = 0.0
    anti_spoof_last_ts:  float = 0.0
    voice_match_conf:    float = 0.0
    voice_sample_count:  int   = 0
    voice_last_heard_ts: float = 0.0
    bootstrap_credits:   int   = 0


@dataclasses.dataclass(slots=True)
class Session:
    # Required (no default)
    person_id:              str
    person_name:            str
    person_type:            str           # "stranger"|"known"|"best_friend"|"disputed"
    session_type:           str           # "face"|"voice"
    started_at:             float
    last_face_seen:         float
    last_spoke_at:          float
    # Optional with defaults
    voice_confidence:       float                 = 1.0
    evidence:               VoiceEvidence         = dataclasses.field(default_factory=VoiceEvidence)
    room_session_id:        str                   = ""
    user_turns:             int                   = 0
    kairos_clock_reset:     bool                  = True
    voice_only_origin:      bool                  = False
    waiting_for_name:       bool                  = False
    voice_face_confirmed:   bool                  = False
    db_enrolled:            bool                  = False
    confidence_tier:        str                   = ""
    prior_person_type:      Optional[str]         = None   # P0.2: None → read as "stranger"
    dispute_reason:         Optional[str]         = None
    disputed_claimed_name:  Optional[str]         = None
    dispute_set_at:         Optional[float]       = None
    disputed_block_count:   int                   = 0
    disputed_block_alerted: bool                  = False
    recent_voice_confs:     list                  = dataclasses.field(default_factory=list)
    cached_prefix:          Optional[str]         = None
    core_memory:            list                  = dataclasses.field(default_factory=list)
    tool_repeat_last:       Optional[str]         = None
    tool_repeat_count:      int                   = 0
    recent_attributions:    list                  = dataclasses.field(default_factory=list)


@dataclasses.dataclass(frozen=True, slots=True)
class SessionSnapshot:
    """Immutable snapshot — safe to hold across await points."""
    person_id:              str
    person_name:            str
    person_type:            str
    session_type:           str
    started_at:             float
    last_face_seen:         float
    last_spoke_at:          float
    voice_confidence:       float
    evidence:               VoiceEvidence         # copied with dataclasses.replace()
    room_session_id:        str
    user_turns:             int
    kairos_clock_reset:     bool
    voice_only_origin:      bool
    waiting_for_name:       bool
    voice_face_confirmed:   bool
    db_enrolled:            bool
    confidence_tier:        str
    prior_person_type:      Optional[str]
    dispute_reason:         Optional[str]
    disputed_claimed_name:  Optional[str]
    dispute_set_at:         Optional[float]
    disputed_block_count:   int
    disputed_block_alerted: bool
    recent_voice_confs:     list           # new list copy (not same reference as Session)
    cached_prefix:          Optional[str]
    core_memory:            list           # new list copy
    tool_repeat_last:       Optional[str]
    tool_repeat_count:      int
    recent_attributions:    list           # new list copy


def _to_snapshot(s: Session) -> SessionSnapshot:
    """Convert mutable Session to immutable SessionSnapshot."""
    return SessionSnapshot(
        person_id=s.person_id,
        person_name=s.person_name,
        person_type=s.person_type,
        session_type=s.session_type,
        started_at=s.started_at,
        last_face_seen=s.last_face_seen,
        last_spoke_at=s.last_spoke_at,
        voice_confidence=s.voice_confidence,
        evidence=dataclasses.replace(s.evidence),  # copy VoiceEvidence
        room_session_id=s.room_session_id,
        user_turns=s.user_turns,
        kairos_clock_reset=s.kairos_clock_reset,
        voice_only_origin=s.voice_only_origin,
        waiting_for_name=s.waiting_for_name,
        voice_face_confirmed=s.voice_face_confirmed,
        db_enrolled=s.db_enrolled,
        confidence_tier=s.confidence_tier,
        prior_person_type=s.prior_person_type,
        dispute_reason=s.dispute_reason,
        disputed_claimed_name=s.disputed_claimed_name,
        dispute_set_at=s.dispute_set_at,
        disputed_block_count=s.disputed_block_count,
        disputed_block_alerted=s.disputed_block_alerted,
        recent_voice_confs=list(s.recent_voice_confs),
        cached_prefix=s.cached_prefix,
        core_memory=list(s.core_memory),
        tool_repeat_last=s.tool_repeat_last,
        tool_repeat_count=s.tool_repeat_count,
        recent_attributions=list(s.recent_attributions),
    )


class SessionStore:
    """Single owner of all active sessions. All mutations are async.

    peek_snapshot() is the ONLY sync read method — safe under:
    1. Single-threaded asyncio (no real thread parallelism).
    2. No sync mutators (all mutations protected by self._lock via async methods).
    3. Returned SessionSnapshot is frozen + slots (safe to hold across await).
    """

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._lock = asyncio.Lock()

    def peek_snapshot(self, pid: str) -> Optional[SessionSnapshot]:
        """SYNC read of session state. Safe under single-threaded asyncio."""
        s = self._sessions.get(pid)
        return _to_snapshot(s) if s is not None else None

    def peek_all_snapshots(self) -> tuple:
        """SYNC read of all active sessions. Safe under single-threaded asyncio."""
        return tuple(_to_snapshot(s) for s in self._sessions.values())

    # --- Reads (async) ---
    async def get_snapshot(self, pid: str) -> Optional[SessionSnapshot]:
        async with self._lock:
            s = self._sessions.get(pid)
            return _to_snapshot(s) if s is not None else None

    # --- Lifecycle ---
    async def open_session(self, person_id: str, person_name: str,
                           person_type: str, session_type: str, *,
                           now: float, bootstrap_credits: int = 0,
                           room_session_id: str = "",
                           voice_sample_count: int = 0) -> None:
        async with self._lock:
            s = Session(
                person_id=person_id, person_name=person_name,
                person_type=person_type, session_type=session_type,
                started_at=now, last_face_seen=now, last_spoke_at=now,
            )
            s.evidence.bootstrap_credits = bootstrap_credits
            s.evidence.voice_sample_count = voice_sample_count
            s.room_session_id = room_session_id
            self._sessions[person_id] = s

    async def close_session(self, pid: str) -> None:
        async with self._lock:
            self._sessions.pop(pid, None)

    async def update_on_reopen(self, pid: str, *, voice_confidence: float,
                               now: Optional[float] = None) -> None:
        async with self._lock:
            s = self._sessions.get(pid)
            if s is not None:
                s.voice_confidence = voice_confidence
                if now is not None:
                    s.last_spoke_at = now
                    s.last_face_seen = now

    # --- Face/voice signals ---
    async def update_face_seen(self, pid: str, *, conf: float, ts: float,
                                anti_spoof_live: Optional[bool] = None,
                                anti_spoof_score: Optional[float] = None) -> None:
        async with self._lock:
            s = self._sessions.get(pid)
            if s is not None:
                s.last_face_seen = ts
                s.evidence.face_match_conf = conf
                s.evidence.face_last_seen_ts = ts
                if anti_spoof_live is not None:
                    s.evidence.anti_spoof_live = anti_spoof_live
                if anti_spoof_score is not None:
                    s.evidence.anti_spoof_score = anti_spoof_score
                if anti_spoof_live is not None or anti_spoof_score is not None:
                    s.evidence.anti_spoof_last_ts = ts

    async def update_voice_heard(self, pid: str, *, conf: float, ts: float) -> None:
        async with self._lock:
            s = self._sessions.get(pid)
            if s is not None:
                s.last_spoke_at = ts
                s.evidence.voice_match_conf = conf
                s.evidence.voice_last_heard_ts = ts

    async def increment_voice_sample_count(self, pid: str) -> None:
        async with self._lock:
            s = self._sessions.get(pid)
            if s is not None:
                s.evidence.voice_sample_count += 1

    async def decrement_bootstrap_credits(self, pid: str) -> None:
        async with self._lock:
            s = self._sessions.get(pid)
            if s is not None:
                s.evidence.bootstrap_credits = max(0, s.evidence.bootstrap_credits - 1)

    async def set_voice_sample_count(self, pid: str, count: int) -> None:
        async with self._lock:
            s = self._sessions.get(pid)
            if s is not None:
                s.evidence.voice_sample_count = count

    async def set_bootstrap_credits(self, pid: str, n: int) -> None:
        async with self._lock:
            s = self._sessions.get(pid)
            if s is not None:
                s.evidence.bootstrap_credits = n

    async def increment_bootstrap_credits(self, pid: str, *, cap: int) -> None:
        async with self._lock:
            s = self._sessions.get(pid)
            if s is not None:
                s.evidence.bootstrap_credits = min(s.evidence.bootstrap_credits + 1, cap)

    async def append_voice_conf(self, pid: str, *, conf: float) -> None:
        async with self._lock:
            s = self._sessions.get(pid)
            if s is not None:
                s.recent_voice_confs.append(conf)

    async def set_last_face_seen(self, pid: str, ts: float) -> None:
        async with self._lock:
            s = self._sessions.get(pid)
            if s is not None:
                s.last_face_seen = ts

    async def set_last_spoke_at(self, pid: str, ts: float) -> None:
        async with self._lock:
            s = self._sessions.get(pid)
            if s is not None:
                s.last_spoke_at = ts

    async def record_voice_spoke(self, pid: str, *, ts: float, voice_confidence: float) -> None:
        async with self._lock:
            s = self._sessions.get(pid)
            if s is not None:
                s.last_spoke_at = ts
                s.voice_confidence = voice_confidence

    async def set_dispute_set_at(self, pid: str, ts: Optional[float]) -> None:
        async with self._lock:
            s = self._sessions.get(pid)
            if s is not None:
                s.dispute_set_at = ts

    # --- Dispute state (atomic) ---
    async def transition_to_disputed(self, pid: str, claimed_name: Optional[str],
                                      reason: str, *, now: float) -> None:
        async with self._lock:
            s = self._sessions.get(pid)
            if s is not None:
                s.prior_person_type = s.person_type  # capture current; P0.2 invariant
                s.person_type = "disputed"
                s.disputed_claimed_name = claimed_name
                s.dispute_reason = reason
                s.dispute_set_at = now

    async def clear_dispute(self, pid: str, *, now: float) -> None:
        async with self._lock:
            s = self._sessions.get(pid)
            if s is not None:
                s.person_type = s.prior_person_type or "stranger"  # fail-closed (P0.2)
                s.prior_person_type = None
                s.dispute_reason = None
                s.disputed_claimed_name = None
                s.dispute_set_at = None
                s.disputed_block_count = 0
                s.disputed_block_alerted = False

    async def increment_block_count(self, pid: str) -> None:
        async with self._lock:
            s = self._sessions.get(pid)
            if s is not None:
                s.disputed_block_count += 1

    async def mark_block_alerted(self, pid: str) -> None:
        async with self._lock:
            s = self._sessions.get(pid)
            if s is not None:
                s.disputed_block_alerted = True

    # --- Name/type ---
    async def rename(self, pid: str, new_name: str) -> None:
        async with self._lock:
            s = self._sessions.get(pid)
            if s is not None:
                s.person_name = new_name

    async def promote_type(self, pid: str, new_type: str) -> None:
        async with self._lock:
            s = self._sessions.get(pid)
            if s is not None:
                s.person_type = new_type

    async def set_waiting_for_name(self, pid: str, value: bool) -> None:
        async with self._lock:
            s = self._sessions.get(pid)
            if s is not None:
                s.waiting_for_name = value

    async def set_voice_only_origin(self, pid: str, value: bool) -> None:
        async with self._lock:
            s = self._sessions.get(pid)
            if s is not None:
                s.voice_only_origin = value

    async def mark_voice_face_confirmed(self, pid: str) -> None:
        async with self._lock:
            s = self._sessions.get(pid)
            if s is not None:
                s.voice_face_confirmed = True

    # --- Turn accounting ---
    async def increment_user_turns(self, pid: str) -> None:
        async with self._lock:
            s = self._sessions.get(pid)
            if s is not None:
                s.user_turns += 1

    async def consume_kairos_reset(self, pid: str) -> None:
        async with self._lock:
            s = self._sessions.get(pid)
            if s is not None:
                s.kairos_clock_reset = False

    async def record_attribution(self, pid: str, label: str) -> None:
        async with self._lock:
            s = self._sessions.get(pid)
            if s is not None:
                s.recent_attributions.append(label)

    async def update_tool_repeat(self, pid: str, repeat_key: Optional[str], count: int) -> None:
        async with self._lock:
            s = self._sessions.get(pid)
            if s is not None:
                s.tool_repeat_last = repeat_key
                s.tool_repeat_count = count

    # --- Cache writes ---
    async def set_cached_prefix(self, pid: str, prefix: Optional[str]) -> None:
        async with self._lock:
            s = self._sessions.get(pid)
            if s is not None:
                s.cached_prefix = prefix

    async def set_core_memory(self, pid: str, memory: list) -> None:
        async with self._lock:
            s = self._sessions.get(pid)
            if s is not None:
                s.core_memory = memory

    async def mark_enrolled(self, pid: str, *, tier: str) -> None:
        async with self._lock:
            s = self._sessions.get(pid)
            if s is not None:
                s.db_enrolled = True
                s.confidence_tier = tier
