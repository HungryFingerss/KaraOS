"""P0.0.7 event log producer — async queue + writer task + serialization.

Public API:
    emit(event_type, payload, *, session_id=..., room_session_id=...,
         parent_event_id=...) -> Optional[int]
    get_drop_count() -> int
    start_writer(db_path=None) -> None
    stop_writer() -> None

Internal invariants (C1 — writer-task scope only):
  - `_recent_parent` cache is mutated ONLY by the writer task (`_flush_one`).
  - `emit()` only enqueues; it never touches `_recent_parent` directly.
  - `_resolve_parent_event_id` / `_record_parent` / `_clear_session_parents`
    are private helpers called by the writer task; the structural test
    `test_recent_parent_only_mutated_by_writer_task` enforces this AST-wise.

Backpressure (D5):
  - 10000-event bounded `asyncio.Queue`.
  - On QueueFull: `_drop_count` increments, log throttled to 1/60s, emit
    returns None. NEVER blocks the producer (lossy under backpressure).
  - `get_drop_count()` exposes the counter for health-log integration.

Test mode (D8):
  - `EVENT_LOG_ENABLED=0` default in fast CI → `emit()` is a no-op.
  - `EVENT_LOG_TESTING=1` switches DB path to `:memory:` and drains
    synchronously per emit (replay-fixture-friendly).

Plan: tests/p0_07_plan_v2.md.
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import os
import sqlite3
import time
import uuid
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from core.event_log.types import (
    EVENT_TYPES,
    NATURAL_PARENT_PAIRS,
    SCHEMA_VERSIONS,
    EventEnvelope,
)


# ──────────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────────

EVENT_LOG_ENABLED: bool = os.environ.get("EVENT_LOG_ENABLED", "0") == "1"
EVENT_LOG_TESTING: bool = os.environ.get("EVENT_LOG_TESTING", "0") == "1"

_EVENT_QUEUE_MAX: int = 10000        # D5 — bounded queue
_DROP_LOG_THROTTLE_SECS: float = 60.0


# ──────────────────────────────────────────────────────────────────────────
# Module-level state
# ──────────────────────────────────────────────────────────────────────────

_queue: Optional[asyncio.Queue] = None
_writer_task: Optional[asyncio.Task] = None
_conn: Optional[sqlite3.Connection] = None
_drop_count: int = 0
_last_drop_log_ts: float = 0.0

# C1 — writer-task-scope cache. Mutated ONLY by `_flush_one`. See module
# docstring. Structural invariant test asserts no other call site mutates
# this dict.
_recent_parent: dict[str, dict[str, int]] = {}


# ──────────────────────────────────────────────────────────────────────────
# JSON serialization (R2)
# ──────────────────────────────────────────────────────────────────────────


def _event_log_default(obj: Any) -> Any:
    """JSON encoder default-handler for event_log payloads.

    Handles types that json.dumps doesn't serialize natively:
      - dataclass instances → dataclasses.asdict (recursive)
      - frozenset / set → sorted list (deterministic for replay diffs)
      - Path → str
      - Enum → .value (primitive)

    Raises TypeError on unhandled types — round-trip contract test
    catches any type that slipped into a payload without a handler.
    """
    if dataclasses.is_dataclass(obj):
        return dataclasses.asdict(obj)
    if isinstance(obj, (frozenset, set)):
        return sorted(obj)
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, Enum):
        return obj.value
    raise TypeError(
        f"event_log: cannot serialize {type(obj).__name__}; "
        f"add a handler in `_event_log_default` or simplify the field."
    )


def _serialize_payload(payload: object) -> bytes:
    """Single canonical serialization path. `sort_keys=True` gives
    byte-deterministic replay diffs across runs."""
    return json.dumps(
        dataclasses.asdict(payload) if dataclasses.is_dataclass(payload) else payload,
        default=_event_log_default,
        sort_keys=True,
    ).encode("utf-8")


# ──────────────────────────────────────────────────────────────────────────
# Parent-event_id resolution (R1 + C1 — writer-task scope only)
# ──────────────────────────────────────────────────────────────────────────


def _resolve_parent_event_id(
    session_id: Optional[str],
    event_type: str,
) -> Optional[int]:
    """Look up the most-recent parent event id for this (session, child)
    pair via NATURAL_PARENT_PAIRS. Returns None when no parent has been
    persisted in this session yet.

    Called by the writer task's `_flush_one` ONLY (C1). Never from emit().
    """
    if session_id is None:
        return None
    session_cache = _recent_parent.get(session_id, {})
    for child, parent_type in NATURAL_PARENT_PAIRS:
        if child == event_type:
            return session_cache.get(parent_type)
    return None


def _record_parent(
    session_id: Optional[str],
    event_type: str,
    event_id: int,
) -> None:
    """Update the per-session cache with the just-assigned id.

    Called by the writer task's `_flush_one` AFTER `cursor.lastrowid` is
    read — guarantees subsequent child events in the same session can
    resolve to this id (single-threaded writer ordering).

    Called by the writer task's `_flush_one` ONLY (C1). Never from emit().
    """
    if session_id is None:
        return
    _recent_parent.setdefault(session_id, {})[event_type] = event_id


def _clear_session_parents(session_id: str) -> None:
    """Drop the per-session parent cache.

    Called by the writer task's `_flush_one` after persisting a
    `session_lifecycle=close` event (C1) — never from emit().
    """
    _recent_parent.pop(session_id, None)


# ──────────────────────────────────────────────────────────────────────────
# Writer task
# ──────────────────────────────────────────────────────────────────────────


def _open_db_connection(db_path: Optional[Path]) -> sqlite3.Connection:
    """Open the SQLite connection. In test mode → :memory:; otherwise the
    provided path (caller supplies BRAIN_DB_PATH in production)."""
    target = ":memory:" if EVENT_LOG_TESTING else str(db_path or ":memory:")
    conn = sqlite3.connect(target, isolation_level="IMMEDIATE")
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """Idempotent CREATE for in-memory test mode. Production DB has the
    table via P0.9 migration `_m_0012_create_event_log_*`; the IF NOT
    EXISTS here is a safety net for test contexts that bypass the
    migration runner."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS event_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            session_id TEXT,
            room_session_id TEXT,
            event_type TEXT NOT NULL,
            schema_version INTEGER NOT NULL DEFAULT 0,
            payload BLOB NOT NULL,
            parent_event_id INTEGER REFERENCES event_log(id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_event_log_ts ON event_log(ts DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_event_log_session ON event_log(session_id, ts)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_event_log_room ON event_log(room_session_id, ts)")
    conn.commit()


def _flush_one(envelope: dict[str, Any]) -> Optional[int]:
    """Persist a single envelope. Returns the assigned id.

    C1: this is the ONLY function that mutates `_recent_parent`. Calls
    `_resolve_parent_event_id` (read) + `_record_parent` (write) +
    `_clear_session_parents` (write on close). Producer's emit() never
    touches `_recent_parent`.
    """
    global _conn
    if _conn is None:
        return None

    event_type = envelope["event_type"]
    session_id = envelope.get("session_id")
    explicit_parent = envelope.get("parent_event_id")

    if explicit_parent is None:
        parent_event_id = _resolve_parent_event_id(session_id, event_type)
    else:
        parent_event_id = explicit_parent

    cursor = _conn.execute(
        """
        INSERT INTO event_log (
            ts, session_id, room_session_id, event_type,
            schema_version, payload, parent_event_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            envelope["ts"],
            session_id,
            envelope.get("room_session_id"),
            event_type,
            envelope["schema_version"],
            envelope["payload"],
            parent_event_id,
        ),
    )
    event_id = cursor.lastrowid
    _conn.commit()

    # Record this id as a candidate parent for downstream children
    # (e.g., audio_in → identity_claim → routing_decision chain).
    _record_parent(session_id, event_type, event_id)

    # Per-session cache cleanup on close.
    if event_type == "session_lifecycle":
        # Inspect the payload to see if this is a close event.
        try:
            payload_obj = json.loads(envelope["payload"])
            if payload_obj.get("lifecycle") == "close" and session_id is not None:
                _clear_session_parents(session_id)
        except (json.JSONDecodeError, AttributeError):
            # Payload should always be valid JSON per _serialize_payload;
            # belt-and-suspenders catch keeps writer task alive.
            pass

    return event_id


async def _writer_loop() -> None:
    """Drain the queue: pull envelopes + _flush_one for each. Exits cleanly
    on `stop_writer()` (sentinel: None envelope in queue)."""
    global _queue
    if _queue is None:
        return
    while True:
        envelope = await _queue.get()
        if envelope is None:
            # Sentinel from stop_writer() — exit cleanly.
            _queue.task_done()
            return
        try:
            _flush_one(envelope)
        except Exception as e:                # pragma: no cover — defensive
            # OBSERVABILITY: never let writer task die silently.
            print(f"[EventLog] writer error: {type(e).__name__}: {e!r}")
        finally:
            _queue.task_done()


# ──────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────


def _build_envelope(
    event_type: str,
    payload: object,
    *,
    session_id: Optional[str],
    room_session_id: Optional[str],
    parent_event_id: Optional[int],
) -> dict[str, Any]:
    """Construct the envelope dict that the writer task consumes."""
    return {
        "ts": time.time(),
        "session_id": session_id,
        "room_session_id": room_session_id,
        "event_type": event_type,
        "schema_version": SCHEMA_VERSIONS.get(event_type, 1),
        "payload": _serialize_payload(payload),
        "parent_event_id": parent_event_id,
    }


def emit_sync(
    event_type: str,
    payload: object,
    *,
    session_id: Optional[str] = None,
    room_session_id: Optional[str] = None,
    parent_event_id: Optional[int] = None,
) -> Optional[int]:
    """Synchronous emission path for sync callers (state.write, FaceDB.log_turn,
    reconcile, _open_session/_close_session, etc.).

    Same contract as `emit` but does not require an awaitable surface. Never
    blocks: in production it does `queue.put_nowait` (lossy under backpressure
    per D5); in test mode (EVENT_LOG_TESTING=1) it drains synchronously to the
    in-memory DB so coverage tests can assert immediately.

    `emit` (async) is a thin wrapper around `emit_sync` for callers in async
    context. Both share the closed-set validation + envelope construction.
    """
    global _queue, _drop_count, _last_drop_log_ts

    if not EVENT_LOG_ENABLED and not EVENT_LOG_TESTING:
        return None

    if event_type not in EVENT_TYPES:
        # D3 invariant violation surfaces at the producer (defense in depth
        # for the structural test in case a producer bypasses the closed set).
        raise ValueError(
            f"event_log: unknown event_type {event_type!r}; "
            f"add to EVENT_TYPES in core/event_log/types.py first."
        )

    envelope = _build_envelope(
        event_type, payload,
        session_id=session_id,
        room_session_id=room_session_id,
        parent_event_id=parent_event_id,
    )

    # In testing mode, drain synchronously per emit so fixture-based tests
    # can assert immediately after the call (no background task needed).
    if EVENT_LOG_TESTING:
        return _flush_one(envelope)

    if _queue is None:
        # Producer was not started — fail-safe no-op.
        return None

    try:
        _queue.put_nowait(envelope)
    except asyncio.QueueFull:
        _drop_count += 1
        now = time.time()
        if now - _last_drop_log_ts >= _DROP_LOG_THROTTLE_SECS:
            _last_drop_log_ts = now
            print(
                f"[EventLog] WARN: dropped event {event_type!r} — queue full "
                f"(total drops={_drop_count})"
            )
        return None

    return None


async def emit(
    event_type: str,
    payload: object,
    *,
    session_id: Optional[str] = None,
    room_session_id: Optional[str] = None,
    parent_event_id: Optional[int] = None,
) -> Optional[int]:
    """Async wrapper around `emit_sync`.

    If `parent_event_id` is None AND `(event_type, ?)` is a child role in
    NATURAL_PARENT_PAIRS, the writer task auto-resolves via
    `_resolve_parent_event_id` at flush time (C1 — writer-task scope).

    Returns None when EVENT_LOG_ENABLED=0 (fast path). When enabled, queues
    the envelope and returns None — the assigned id is captured by the
    writer task and surfaced via `_recent_parent` for natural-pair
    resolution. Callers wanting synchronous id retrieval should use the
    replay fixture's in-memory mode (EVENT_LOG_TESTING=1).
    """
    return emit_sync(
        event_type, payload,
        session_id=session_id,
        room_session_id=room_session_id,
        parent_event_id=parent_event_id,
    )


def _ensure_frames_dir() -> Path:
    """Ensure faces/frames/ exists for vision_frame JPEG sidecar storage.

    Called by start_writer + the H2 producer hook. Returns the absolute
    directory path so hook code can write files into it.
    """
    # Resolve relative to repo root (current working dir during pipeline boot).
    frames_dir = Path("faces") / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    return frames_dir


def safe_emit_sync(
    event_type: str,
    payload: object,
    *,
    session_id: Optional[str] = None,
    room_session_id: Optional[str] = None,
    parent_event_id: Optional[int] = None,
) -> Optional[int]:
    """Fire-and-forget emit for production hook call sites.

    Wraps `emit_sync` in a single try/except that swallows ALL exceptions.
    Same contract semantics as `emit_sync` except errors never propagate —
    event-log emission is best-effort observability, and a producer-hook
    bug must NEVER break the production path it instruments.

    Hook call sites (11 hooks, 12 call sites — H7 emits both tool_call +
    tool_result) all use this helper. The single annotated except block
    here satisfies P0.4's silent-except invariant for the entire hook
    surface; future hooks land via this helper and inherit the
    discipline automatically (same shape as P0.8's _TOOL_HANDLERS
    consolidation).

    Strict `emit_sync` remains the right call for tests + replay tools
    that want to surface contract violations (e.g. D3 unknown event_type).
    """
    try:
        return emit_sync(
            event_type, payload,
            session_id=session_id,
            room_session_id=room_session_id,
            parent_event_id=parent_event_id,
        )
    except Exception as _e:
        # OPTIONAL: event-log emission is best-effort observability —
        # producer-hook errors must not break the production path.
        # Logged at WARN once-per-process so a recurring producer bug
        # surfaces in operator logs without spamming.
        global _safe_emit_failure_count
        _safe_emit_failure_count += 1
        if _safe_emit_failure_count <= 3:
            print(
                f"[EventLog] WARN: safe_emit_sync swallowed exception for "
                f"{event_type!r}: {type(_e).__name__}: {_e!r} "
                f"(count={_safe_emit_failure_count})"
            )
        return None


_safe_emit_failure_count: int = 0


def get_safe_emit_failure_count() -> int:
    """Return number of exceptions swallowed by safe_emit_sync since
    process start. Useful for health-log integration alongside drop count."""
    return _safe_emit_failure_count


def get_drop_count() -> int:
    """Number of events dropped due to backpressure since process start.

    Exposed for `core.health.gather_health_snapshot` integration (D5).
    Health log emits `event_log_drops=N` field; non-zero increments fire
    a watch alert. NO `event_log_dropped` event is emitted in the queue
    (D5 circular-dependency guard).
    """
    return _drop_count


async def start_writer(db_path: Optional[Path] = None) -> None:
    """Start the background writer task. Called once during pipeline boot.

    `db_path` is the brain.db path in production. In test mode
    (EVENT_LOG_TESTING=1) the parameter is ignored — :memory: SQLite
    is used so fixtures get a clean DB per test.
    """
    global _queue, _writer_task, _conn
    if _writer_task is not None and not _writer_task.done():
        return  # already running

    _queue = asyncio.Queue(maxsize=_EVENT_QUEUE_MAX)
    _conn = _open_db_connection(db_path)
    _ensure_schema(_conn)
    # H2 prerequisite: faces/frames/ exists before the vision-loop sidecar
    # starts writing JPEGs. Hash-keyed filenames give us free dedup.
    _ensure_frames_dir()
    _writer_task = asyncio.create_task(_writer_loop())


async def stop_writer() -> None:
    """Drain the queue + shutdown. Called during graceful pipeline exit.

    P0.B5 D2 (Bug 8) fix: wrap `_queue.join()` with `asyncio.wait_for` to
    bound the wait when `_writer_task` has died before sentinel put. Pre-fix:
    `await _queue.join()` blocked forever because no consumer was calling
    `task_done()`. Post-fix: timeout proceeds to cleanup; subsequent
    `wait_for(_writer_task, ...)` surfaces the dead task via cancel path.
    """
    global _queue, _writer_task, _conn, _recent_parent

    # P0.B5 D2: early-exit if writer task is already done. Don't put sentinel
    # into a queue with no consumer (would just inflate the queue size + lose
    # envelopes anyway on cleanup).
    if _writer_task is not None and _writer_task.done():
        if _queue is not None:
            _q_size = _queue.qsize()
            print(
                f"[EventLog] WARN: stop_writer found writer task already done — "
                f"skipping queue drain ({_q_size} envelopes lost)"
            )
        # Fall through to cleanup below
    elif _queue is not None:
        # Sentinel: None envelope tells _writer_loop to exit.
        await _queue.put(None)
        # P0.B5 D2: bounded wait — protects against writer-task-died-mid-shutdown.
        try:
            await asyncio.wait_for(_queue.join(), timeout=5.0)
        except asyncio.TimeoutError:
            print(
                f"[EventLog] WARN: stop_writer queue.join() timed out — "
                f"writer task likely dead, proceeding to cleanup"
            )

    if _writer_task is not None:
        try:
            await asyncio.wait_for(_writer_task, timeout=5.0)
        except asyncio.TimeoutError:                       # pragma: no cover
            _writer_task.cancel()
        except asyncio.CancelledError:
            # P0.B5 D2 (Phase 4 in-flight refinement): if the task was already
            # cancelled BEFORE stop_writer was called (early-exit branch above
            # observed `_writer_task.done()`), awaiting it re-raises the
            # CancelledError. Swallow it here — cleanup must complete.
            pass
    if _conn is not None:
        _conn.close()
    _queue = None
    _writer_task = None
    _conn = None
    _recent_parent = {}


# Test-only helpers — explicitly named so production callers don't reach for
# them by accident. Replay fixture uses these to seed + clear state.

def _reset_for_tests() -> None:
    """Test-mode reset. Closes DB + clears module state."""
    global _queue, _writer_task, _conn, _drop_count, _recent_parent, _last_drop_log_ts, _safe_emit_failure_count
    #                                                                                   ^^^^^^^^^^^^^^^^^^^^^^^^
    #                                                                                   P0.B5 D1 — Bug 7 fix
    if _conn is not None:
        try:
            _conn.close()
        except Exception:                          # pragma: no cover
            # CLEANUP: best-effort close.
            pass
    _queue = None
    _writer_task = None
    _conn = None
    _drop_count = 0
    _recent_parent = {}
    _last_drop_log_ts = 0.0
    _safe_emit_failure_count = 0  # P0.B5 D1 — Bug 7 fix (test isolation)


def _open_testing_db_sync() -> None:
    """Test-mode sync setup: open the in-memory DB + create schema so
    EVENT_LOG_TESTING=1 paths can emit without an asyncio loop."""
    global _conn
    if _conn is not None:
        return
    _conn = _open_db_connection(None)
    _ensure_schema(_conn)


def _query_all_events_for_tests() -> list[dict[str, Any]]:
    """Test-mode read-back: return every row in event_log as a dict.
    Used by the replay fixture to assert emission outcomes."""
    if _conn is None:
        return []
    rows = _conn.execute(
        "SELECT id, ts, session_id, room_session_id, event_type, "
        "schema_version, payload, parent_event_id FROM event_log ORDER BY id"
    ).fetchall()
    return [
        {
            "id": r[0],
            "ts": r[1],
            "session_id": r[2],
            "room_session_id": r[3],
            "event_type": r[4],
            "schema_version": r[5],
            "payload": json.loads(r[6]) if r[6] else None,
            "parent_event_id": r[7],
        }
        for r in rows
    ]


__all__ = [
    "EVENT_LOG_ENABLED",
    "EVENT_LOG_TESTING",
    "emit",
    "emit_sync",
    "safe_emit_sync",
    "get_drop_count",
    "get_safe_emit_failure_count",
    "start_writer",
    "stop_writer",
]
