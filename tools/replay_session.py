"""P0.0.7 Step 6 — read-only replay CLI for event_log.

Inspects events captured by `core.event_log.producer` from a live or
archived brain.db. Per Plan v2 Block D the v1 ship is a pretty-printer
for human inspection; the full-pipeline replay sink is bookmarked for
P0.S1's anti-spoof regression test work.

Usage:

    python tools/replay_session.py                          # default brain.db
    python tools/replay_session.py --session jagan_001
    python tools/replay_session.py --room room_123 --since 1h
    python tools/replay_session.py --type tool_call --limit 50
    python tools/replay_session.py --db /alt/path/brain.db

Filters compose (AND semantics). Parent-pair events render indented
under their parent so audio_in → identity_claim → routing_decision (and
tool_call → tool_result) read as a tree.

Side effects: ZERO. The CLI opens brain.db in read-only URI mode
(`file:<path>?mode=ro`) and never writes. Safe to run against a live
production DB while the pipeline is running.

Plan: tests/p0_07_plan_v2.md.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Iterable, Optional


# Resolve repo root so the producer's types module is importable regardless
# of where the CLI is invoked from.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Import after sys.path is set up.
from core.event_log.types import (  # noqa: E402
    EVENT_TYPES,
    NATURAL_PARENT_PAIRS,
    SCHEMA_VERSIONS,
    _PAYLOAD_CLASSES,
)


# Default brain.db path mirrors core.config.BRAIN_DB_PATH conventions
# without importing core.config (which drags heavy deps).
_DEFAULT_BRAIN_DB = _REPO_ROOT / "faces" / "brain.db"


# ──────────────────────────────────────────────────────────────────────────
# Argument parsing
# ──────────────────────────────────────────────────────────────────────────


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="replay_session",
        description=(
            "Pretty-print event_log entries from brain.db. Read-only; "
            "safe against a live production DB."
        ),
    )
    p.add_argument(
        "--db", type=Path, default=_DEFAULT_BRAIN_DB,
        help=f"Path to brain.db (default: {_DEFAULT_BRAIN_DB})",
    )
    p.add_argument(
        "--session", default=None,
        help="Filter by session_id (e.g. jagan_001)",
    )
    p.add_argument(
        "--room", default=None,
        help="Filter by room_session_id (e.g. room_1779_abc)",
    )
    p.add_argument(
        "--type", dest="event_type", default=None,
        choices=sorted(EVENT_TYPES),
        help="Filter to one event_type",
    )
    p.add_argument(
        "--since", default=None,
        help=(
            "Filter to events newer than this offset. Accepts: a Unix "
            "timestamp (e.g. 1779008461), an ISO-like string, or a duration "
            "suffix (1m, 30m, 1h, 24h, 7d) relative to now."
        ),
    )
    p.add_argument(
        "--limit", type=int, default=200,
        help="Maximum events to render (default 200; 0 = no limit)",
    )
    p.add_argument(
        "--no-tree", action="store_true",
        help=(
            "Disable natural-pair tree rendering — print every event flat "
            "with no indentation. Useful for grep / piping to other tools."
        ),
    )
    p.add_argument(
        "--raw-payload", action="store_true",
        help=(
            "Print the full JSON payload after each line instead of the "
            "one-line summary. Useful for debugging payload-shape issues."
        ),
    )
    return p


def _parse_since(value: str) -> float:
    """Parse a --since argument into a Unix timestamp."""
    # Duration suffix? (e.g. 1h, 30m, 7d)
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)([smhd])\s*", value)
    if m:
        amount = float(m.group(1))
        unit = m.group(2)
        seconds = {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]
        return time.time() - amount * seconds
    # Numeric timestamp?
    try:
        return float(value)
    except ValueError:
        pass
    # ISO-like fallback (very lenient — let datetime parse it).
    try:
        from datetime import datetime
        return datetime.fromisoformat(value).timestamp()
    except (ValueError, ImportError):
        raise SystemExit(
            f"replay_session: cannot parse --since {value!r}. Accepted: "
            "Unix timestamp / ISO datetime / duration suffix (1m, 30m, 1h, 24h, 7d)."
        )


# ──────────────────────────────────────────────────────────────────────────
# Database access (read-only)
# ──────────────────────────────────────────────────────────────────────────


def _open_readonly(db_path: Path) -> sqlite3.Connection:
    """Open brain.db in URI read-only mode. Raises if path doesn't exist."""
    if not db_path.exists():
        raise SystemExit(
            f"replay_session: brain.db not found at {db_path}. "
            f"Pass --db <path> to point at an alternate DB."
        )
    uri = f"file:{db_path.as_posix()}?mode=ro"
    return sqlite3.connect(uri, uri=True, isolation_level=None)


def _query_events(
    conn: sqlite3.Connection,
    *,
    session: Optional[str],
    room: Optional[str],
    event_type: Optional[str],
    since: Optional[float],
    limit: int,
) -> list[dict[str, Any]]:
    """Build the WHERE clause from filters; return events in chronological order."""
    where_clauses: list[str] = []
    params: list[Any] = []
    if session is not None:
        where_clauses.append("session_id = ?")
        params.append(session)
    if room is not None:
        where_clauses.append("room_session_id = ?")
        params.append(room)
    if event_type is not None:
        where_clauses.append("event_type = ?")
        params.append(event_type)
    if since is not None:
        where_clauses.append("ts >= ?")
        params.append(since)
    where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    limit_sql = f" LIMIT {int(limit)}" if limit and limit > 0 else ""

    sql = (
        "SELECT id, ts, session_id, room_session_id, event_type, "
        "schema_version, payload, parent_event_id "
        f"FROM event_log{where_sql} ORDER BY ts ASC, id ASC{limit_sql}"
    )
    try:
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError as e:
        if "no such table" in str(e).lower():
            raise SystemExit(
                "replay_session: brain.db has no event_log table. The P0.0.7 "
                "migration (_m_0012_create_event_log_*) hasn't applied to "
                "this DB. Open the pipeline at least once with EVENT_LOG_ENABLED=1 "
                "to bootstrap the table."
            )
        raise

    return [
        {
            "id": r[0],
            "ts": r[1],
            "session_id": r[2],
            "room_session_id": r[3],
            "event_type": r[4],
            "schema_version": r[5],
            "payload_json": r[6],
            "parent_event_id": r[7],
        }
        for r in rows
    ]


# ──────────────────────────────────────────────────────────────────────────
# Payload summarisation (one-liners per event_type)
# ──────────────────────────────────────────────────────────────────────────


def _truncate(s: str, limit: int = 60) -> str:
    s = (s or "").replace("\n", " ").strip()
    return s if len(s) <= limit else s[: limit - 3] + "..."


def _summarize_payload(event_type: str, schema_version: int, payload_dict: dict) -> str:
    """Render a one-line summary using the dispatch-table dataclass.

    Falls back to a minimal JSON dump when dispatch lookup fails (corrupt
    row or future event_type the dispatch table doesn't yet know).
    """
    cls = _PAYLOAD_CLASSES.get((event_type, schema_version))
    try:
        obj = cls.from_json_dict(payload_dict, schema_version=schema_version) if cls else None
    except Exception:
        obj = None

    if obj is None:
        # Last-resort: render a JSON-ish summary so the line still says
        # something useful even when dispatch fails.
        return _truncate(json.dumps(payload_dict, default=str, sort_keys=True))

    if event_type == "audio_in":
        return f'"{_truncate(obj.stt_text)}" ({obj.language}, {obj.speech_secs:.2f}s)'
    if event_type == "vision_frame":
        rec = (
            ",".join(f"{pid}@{score:.2f}" for pid, score, _q in obj.recognized[:3])
            or "none"
        )
        return (
            f"frame={obj.frame_id} dets={obj.n_detections} "
            f"recognized=[{rec}] "
            f"anti_spoof={'live' if obj.anti_spoof_live else 'spoof'}"
        )
    if event_type == "identity_claim":
        c = obj.claim
        return (
            f"pid={c.pid!r} conf={c.confidence:.3f} "
            f"n_seg={c.n_diarize_segments} utt={c.utterance_duration:.2f}s"
        )
    if event_type == "presence_state":
        p = obj.presence
        return (
            f"visible={list(p.visible_pids) or 'none'} "
            f"unrec_tracks={list(p.unrecognized_track_ids) or 'none'}"
        )
    if event_type == "routing_decision":
        d = obj.decision
        return (
            f"action={d.action} pid={d.pid!r} rule={d.rule_fired!r} "
            f"utt_band={obj.utt_band}"
        )
    if event_type == "intent_classification":
        s = obj.sidecar or {}
        intent = s.get("turn_intent", "?")
        conf = s.get("confidence", 0.0)
        try:
            conf_str = f"{float(conf):.2f}"
        except (TypeError, ValueError):
            conf_str = str(conf)
        return (
            f'intent={intent} conf={conf_str} mode={obj.mode} '
            f'text="{_truncate(obj.text, 40)}"'
            + (" (cached)" if obj.from_cache else "")
        )
    if event_type == "tool_call":
        args_str = _truncate(json.dumps(obj.args, default=str, sort_keys=True), 40)
        return f"name={obj.name} person={obj.person_id!r} args={args_str}"
    if event_type == "tool_result":
        err = f" error={obj.error!r}" if obj.error else ""
        return f"status={obj.status}{err}"
    if event_type == "memory_write":
        return f"role={obj.role} pid={obj.person_id!r} text=\"{_truncate(obj.text, 40)}\""
    if event_type == "state_write":
        return (
            f"mode={obj.mode} current_person={obj.current_person!r} "
            f"visible={list(obj.visible_people) or 'none'}"
        )
    if event_type == "tts_out":
        stream = " (stream)" if obj.was_stream else ""
        dur = f" {obj.duration_ms_est}ms" if obj.duration_ms_est is not None else ""
        return f'"{_truncate(obj.text, 50)}" ({obj.language}{dur}){stream} purpose={obj.purpose}'
    if event_type == "session_lifecycle":
        return (
            f"lifecycle={obj.lifecycle} pid={obj.person_id!r} "
            f"name={obj.person_name!r} type={obj.person_type} "
            f"source={obj.source}"
        )

    # Unknown event_type — shouldn't happen given the closed set, but be defensive.
    return _truncate(json.dumps(payload_dict, default=str, sort_keys=True))


# ──────────────────────────────────────────────────────────────────────────
# Rendering
# ──────────────────────────────────────────────────────────────────────────


def _fmt_ts(ts: float) -> str:
    """Render a Unix timestamp as `HH:MM:SS.mmm` for terminal-friendly output."""
    lt = time.localtime(ts)
    ms = int((ts - int(ts)) * 1000)
    return f"{lt.tm_hour:02d}:{lt.tm_min:02d}:{lt.tm_sec:02d}.{ms:03d}"


def _format_event_line(
    event: dict[str, Any],
    *,
    indent: int = 0,
    raw_payload: bool = False,
) -> str:
    indent_str = "  " * indent + ("└─ " if indent > 0 else "")
    try:
        payload_dict = json.loads(event["payload_json"]) if event["payload_json"] else {}
    except (json.JSONDecodeError, TypeError):
        payload_dict = {}
    summary = _summarize_payload(
        event["event_type"], event["schema_version"], payload_dict,
    )
    pid_str = f" session={event['session_id']!r}" if event["session_id"] else ""
    room_str = f" room={event['room_session_id']!r}" if event["room_session_id"] else ""
    parent_str = (
        f" parent={event['parent_event_id']}"
        if event["parent_event_id"] is not None else ""
    )
    head = (
        f"{indent_str}[{_fmt_ts(event['ts'])}] id={event['id']:<5} "
        f"{event['event_type']:<22}{pid_str}{room_str}{parent_str}"
    )
    body = f" → {summary}"
    line = head + body
    if raw_payload:
        line += "\n" + " " * (len(indent_str) + 4) + json.dumps(
            payload_dict, sort_keys=True
        )
    return line


def _render(events: Iterable[dict[str, Any]], *, tree: bool = True,
            raw_payload: bool = False) -> Iterable[str]:
    """Yield formatted lines for the event stream."""
    if not tree:
        for ev in events:
            yield _format_event_line(ev, indent=0, raw_payload=raw_payload)
        return

    # Tree mode: index by id so we can detect when a parent is in-window.
    event_list = list(events)
    in_window = {ev["id"] for ev in event_list}
    for ev in event_list:
        parent = ev["parent_event_id"]
        indent = 1 if (parent is not None and parent in in_window) else 0
        yield _format_event_line(ev, indent=indent, raw_payload=raw_payload)


# ──────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────


def _print_header(args: argparse.Namespace, n: int) -> None:
    parts = [f"replay_session: {n} event(s) from {args.db}"]
    if args.session:
        parts.append(f"session={args.session}")
    if args.room:
        parts.append(f"room={args.room}")
    if args.event_type:
        parts.append(f"type={args.event_type}")
    if args.since:
        parts.append(f"since={args.since}")
    if args.limit and args.limit > 0:
        parts.append(f"limit={args.limit}")
    print(" | ".join(parts))
    print("-" * 78)


def _ensure_utf8_stdout() -> None:
    """Reconfigure stdout to UTF-8 so the Unicode arrow (→) + tree
    characters (└─) print on Windows cp1252 terminals. No-op on streams
    that don't support reconfigure() (Python 3.6 and earlier — not a
    concern here, repo targets 3.13)."""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        # CLEANUP: best-effort — tests sometimes wrap stdout with a
        # non-TextIOWrapper that lacks reconfigure(); fall back silently.
        pass


def main(argv: Optional[list[str]] = None) -> int:
    _ensure_utf8_stdout()
    args = _build_arg_parser().parse_args(argv)

    since_ts: Optional[float] = _parse_since(args.since) if args.since else None

    conn = _open_readonly(args.db)
    try:
        events = _query_events(
            conn,
            session=args.session,
            room=args.room,
            event_type=args.event_type,
            since=since_ts,
            limit=args.limit,
        )
    finally:
        conn.close()

    _print_header(args, len(events))
    for line in _render(
        events, tree=(not args.no_tree), raw_payload=args.raw_payload,
    ):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
