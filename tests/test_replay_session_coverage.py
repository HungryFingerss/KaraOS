"""Coverage-to-100 campaign — tools/replay_session.py.

Exercises every uncovered line/branch of the read-only event_log replay
CLI: arg parsing, --since parsing (duration/timestamp/ISO/invalid),
read-only DB open, filtered queries (incl. since + no-such-table + generic
OperationalError re-raise), per-event-type payload summarisation (every
branch + the dispatch-fail fallback + the unknown-event_type fallback),
event-line formatting (indent, malformed payload, raw-payload), tree vs
flat rendering, header printing, UTF-8 stdout reconfigure, and main().

Headless: no GPU/camera/network/model downloads. The module is side-loaded
via importlib (tools/ is a script dir, not a package); DB access uses a
tmp file-backed sqlite via the real v12 migration + direct inserts, so the
heavy producer machinery is never touched.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import argparse
import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_REPLAY_PATH = _REPO_ROOT / "tools" / "replay_session.py"

def _load_replay_module(module_name: str):
    """Side-load tools/replay_session.py under a chosen module name."""
    spec = importlib.util.spec_from_file_location(module_name, _REPLAY_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module

@pytest.fixture(scope="module")
def replay_cli():
    """Load the CLI module once for the whole test module."""
    return _load_replay_module("replay_session_cov")

# ──────────────────────────────────────────────────────────────────────────
# Representative payload dicts — one per event_type (shapes match each
# from_json_dict's expected keys).
# ──────────────────────────────────────────────────────────────────────────

_AUDIO_IN = {
    "audio_hash": "h", "speech_secs": 1.23, "stt_text": "hello there",
    "language": "en", "pre_roll_ms": 100,
}
_VISION_LIVE = {
    "frame_id": "f1", "frame_path": None, "frame_ts": 1.0, "n_detections": 2,
    "recognized": [["jagan", 0.9, 0.8], ["lexi", 0.7, 0.6]],
    "unrecognized_track_ids": [3], "anti_spoof_live": True,
    "anti_spoof_score": 0.95,
}
_VISION_SPOOF_EMPTY = {
    "frame_id": "f2", "frame_path": None, "frame_ts": 1.0, "n_detections": 0,
    "recognized": [], "unrecognized_track_ids": [], "anti_spoof_live": False,
    "anti_spoof_score": None,
}
_IDENTITY_CLAIM = {
    "claim": {
        "pid": "jagan", "confidence": 0.88, "n_diarize_segments": 2,
        "utterance_duration": 1.5, "reasoning": "", "raw_segment_scores": [],
        "confidence_is_no_signal": False,
    }
}
_PRESENCE = {
    "presence": {
        "visible_pids": ["jagan"], "unrecognized_track_ids": [4],
        "per_pid_confidence": {}, "per_pid_quality": {}, "frame_ts": 0.0,
        "reasoning": "",
    }
}
_PRESENCE_EMPTY = {
    "presence": {
        "visible_pids": [], "unrecognized_track_ids": [],
        "per_pid_confidence": {}, "per_pid_quality": {}, "frame_ts": 0.0,
        "reasoning": "",
    }
}
_ROUTING = {
    "decision": {"pid": "jagan", "action": "current", "reasoning": "",
                 "rule_fired": "r"},
    "utt_band": "normal",
}
_INTENT_CACHED = {
    "sidecar": {"turn_intent": "casual", "confidence": 0.92},
    "mode": "shadow", "text": "some text here", "from_cache": True,
}
_INTENT_BADCONF = {
    "sidecar": {"turn_intent": "x", "confidence": "NaNstr"},
    "mode": "primary", "text": "t", "from_cache": False,
}
_TOOL_CALL = {
    "name": "update_person_name", "args": {"name": "Jagan"},
    "person_id": "jagan", "intent_sidecar": None,
}
_TOOL_RESULT_ERR = {"status": "handled", "response_text": None, "error": "boom"}
_TOOL_RESULT_OK = {"status": "ok", "response_text": "r", "error": None}
_MEMORY = {
    "person_id": "jagan", "role": "user", "text": "remember this",
    "room_session_id": None, "audience_ids": None,
}
_STATE = {
    "mode": "WATCHING", "current_person": "jagan",
    "current_person_id": "jagan", "visible_people": ["jagan"], "message": "",
}
_STATE_EMPTY = {
    "mode": "WATCHING", "current_person": None, "current_person_id": None,
    "visible_people": [], "message": "",
}
_TTS_STREAM = {
    "text": "spoken words", "text_full_hash": "x", "language": "en",
    "was_stream": True, "purpose": "reply", "duration_ms_est": 1200,
}
_TTS_PLAIN = {
    "text": "spoken words", "text_full_hash": "x", "language": "en",
    "was_stream": False, "purpose": "reply", "duration_ms_est": None,
}
_LIFECYCLE = {
    "lifecycle": "open", "person_id": "jagan", "person_name": "Jagan",
    "source": "voice", "person_type": "known", "room_session_id": None,
}

def _make_db(tmp_path: Path, rows) -> Path:
    """Build a tmp file-backed brain.db with the v12 event_log schema."""
    from core.brain_db_migrations import _m_0012_create_event_log_apply

    db = tmp_path / "brain.db"
    conn = sqlite3.connect(str(db))
    _m_0012_create_event_log_apply(conn)
    conn.commit()
    conn.executemany(
        "INSERT INTO event_log (id, ts, session_id, room_session_id, "
        "event_type, schema_version, payload, parent_event_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()
    return db

# ══════════════════════════════════════════════════════════════════════════
# Module-level sys.path insertion (line 46)
# ══════════════════════════════════════════════════════════════════════════

def test_module_inserts_repo_root_into_syspath_when_missing():
    """Line 45-46: when repo root is absent from sys.path, the module
    inserts it. Force the branch by removing it, then re-loading fresh."""
    import core.event_log.types  # noqa: F401 — warm the import cache first

    repo_root = str(_REPO_ROOT)
    saved_path = list(sys.path)
    saved_mod = sys.modules.pop("_rs_line46", None)
    try:
        sys.path[:] = [p for p in sys.path if p != repo_root]
        assert repo_root not in sys.path
        mod = _load_replay_module("_rs_line46")
        assert repo_root in sys.path, "line 46 should have inserted repo root"
        assert callable(getattr(mod, "main"))
    finally:
        sys.path[:] = saved_path
        sys.modules.pop("_rs_line46", None)
        if saved_mod is not None:
            sys.modules["_rs_line46"] = saved_mod

# ══════════════════════════════════════════════════════════════════════════
# _build_arg_parser (68-118)
# ══════════════════════════════════════════════════════════════════════════

def test_build_arg_parser_defaults(replay_cli):
    parser = replay_cli._build_arg_parser()
    args = parser.parse_args([])
    assert args.db == replay_cli._DEFAULT_BRAIN_DB
    assert args.session is None
    assert args.room is None
    assert args.event_type is None
    assert args.since is None
    assert args.limit == 200
    assert args.no_tree is False
    assert args.raw_payload is False

def test_build_arg_parser_all_flags(replay_cli):
    parser = replay_cli._build_arg_parser()
    args = parser.parse_args([
        "--db", "/tmp/x.db", "--session", "jagan_001", "--room", "room_1",
        "--type", "audio_in", "--since", "1h", "--limit", "50",
        "--no-tree", "--raw-payload",
    ])
    assert str(args.db) in ("/tmp/x.db", "\\tmp\\x.db") or args.db == Path("/tmp/x.db")
    assert args.session == "jagan_001"
    assert args.room == "room_1"
    assert args.event_type == "audio_in"
    assert args.since == "1h"
    assert args.limit == 50
    assert args.no_tree is True
    assert args.raw_payload is True

def test_build_arg_parser_rejects_bad_event_type(replay_cli):
    parser = replay_cli._build_arg_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--type", "not_a_real_type"])

# ══════════════════════════════════════════════════════════════════════════
# _parse_since (121-143)
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("value,unit_secs", [
    ("1s", 1), ("30m", 1800), ("1h", 3600), ("7d", 604800), ("1.5h", 5400),
])
def test_parse_since_duration_suffix(replay_cli, value, unit_secs):
    import time as _t
    before = _t.time()
    got = replay_cli._parse_since(value)
    after = _t.time()
    # got == now - unit_secs, computed inside the call
    assert (before - unit_secs) - 1 <= got <= (after - unit_secs) + 1

def test_parse_since_numeric_timestamp(replay_cli):
    assert replay_cli._parse_since("1779008461") == 1779008461.0
    assert replay_cli._parse_since("1779008461.5") == 1779008461.5

def test_parse_since_iso_fallback(replay_cli):
    from datetime import datetime
    got = replay_cli._parse_since("2026-06-01")
    assert got == datetime.fromisoformat("2026-06-01").timestamp()

def test_parse_since_iso_datetime_fallback(replay_cli):
    from datetime import datetime
    got = replay_cli._parse_since("2026-06-01T12:30:00")
    assert got == datetime.fromisoformat("2026-06-01T12:30:00").timestamp()

def test_parse_since_invalid_raises_systemexit(replay_cli):
    with pytest.raises(SystemExit) as ei:
        replay_cli._parse_since("definitely-not-a-date")
    assert "cannot parse --since" in str(ei.value)

# ══════════════════════════════════════════════════════════════════════════
# _open_readonly (151-159)
# ══════════════════════════════════════════════════════════════════════════

def test_open_readonly_missing_path_raises_systemexit(replay_cli, tmp_path):
    missing = tmp_path / "does_not_exist.db"
    with pytest.raises(SystemExit) as ei:
        replay_cli._open_readonly(missing)
    assert "brain.db not found" in str(ei.value)

def test_open_readonly_returns_connection(replay_cli, tmp_path):
    db = _make_db(tmp_path, [])
    conn = replay_cli._open_readonly(db)
    try:
        assert isinstance(conn, sqlite3.Connection)
    finally:
        conn.close()

# ══════════════════════════════════════════════════════════════════════════
# _query_events (162-218)
# ══════════════════════════════════════════════════════════════════════════

def test_query_events_filters_and_since(replay_cli, tmp_path):
    rows = [
        (1, 100.0, "jagan_001", None, "audio_in", 1,
         json.dumps(_AUDIO_IN), None),
        (2, 200.0, "jagan_001", "room_x", "tool_call", 1,
         json.dumps(_TOOL_CALL), 1),
        (3, 300.0, "lexi_002", "room_y", "memory_write", 1,
         json.dumps(_MEMORY), None),
    ]
    db = _make_db(tmp_path, rows)
    conn = replay_cli._open_readonly(db)
    try:
        # session + since combine (AND) — only id=2 (ts=200 >= 150, session match)
        got = replay_cli._query_events(
            conn, session="jagan_001", room=None, event_type=None,
            since=150.0, limit=0,
        )
        assert [e["id"] for e in got] == [2]
        # room filter
        got = replay_cli._query_events(
            conn, session=None, room="room_y", event_type=None,
            since=None, limit=0,
        )
        assert [e["id"] for e in got] == [3]
        # event_type filter + limit>0
        got = replay_cli._query_events(
            conn, session=None, room=None, event_type="audio_in",
            since=None, limit=5,
        )
        assert [e["id"] for e in got] == [1]
        # no filters, limit=0 → all, and dict shape is complete
        got = replay_cli._query_events(
            conn, session=None, room=None, event_type=None,
            since=None, limit=0,
        )
        assert [e["id"] for e in got] == [1, 2, 3]
        assert set(got[0].keys()) == {
            "id", "ts", "session_id", "room_session_id", "event_type",
            "schema_version", "payload_json", "parent_event_id",
        }
    finally:
        conn.close()

def test_query_events_no_such_table_raises_systemexit(replay_cli, tmp_path):
    # A valid sqlite DB but WITHOUT the event_log table.
    empty = tmp_path / "empty.db"
    sqlite3.connect(str(empty)).close()
    conn = replay_cli._open_readonly(empty)
    try:
        with pytest.raises(SystemExit) as ei:
            replay_cli._query_events(
                conn, session=None, room=None, event_type=None,
                since=None, limit=0,
            )
        assert "no event_log table" in str(ei.value)
    finally:
        conn.close()

def test_query_events_other_operational_error_reraises(replay_cli):
    class _FakeConn:
        def execute(self, sql, params):
            raise sqlite3.OperationalError("database is locked")

    with pytest.raises(sqlite3.OperationalError) as ei:
        replay_cli._query_events(
            _FakeConn(), session=None, room=None, event_type=None,
            since=None, limit=0,
        )
    assert "database is locked" in str(ei.value)

# ══════════════════════════════════════════════════════════════════════════
# _truncate (226-228)
# ══════════════════════════════════════════════════════════════════════════

def test_truncate_short_and_long_and_none(replay_cli):
    assert replay_cli._truncate("hi") == "hi"
    assert replay_cli._truncate(None) == ""
    long = "x" * 100
    out = replay_cli._truncate(long, limit=10)
    assert out.endswith("...") and len(out) == 10
    # newline collapse + strip
    assert replay_cli._truncate("  a\nb  ") == "a b"

# ══════════════════════════════════════════════════════════════════════════
# _summarize_payload — every branch (231-316)
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("event_type,payload,expected", [
    ("audio_in", _AUDIO_IN, "hello there"),
    ("vision_frame", _VISION_LIVE, "anti_spoof=live"),
    ("vision_frame", _VISION_SPOOF_EMPTY, "anti_spoof=spoof"),
    ("vision_frame", _VISION_SPOOF_EMPTY, "recognized=[none]"),
    ("identity_claim", _IDENTITY_CLAIM, "pid='jagan'"),
    ("presence_state", _PRESENCE, "visible=['jagan']"),
    ("presence_state", _PRESENCE_EMPTY, "visible=none"),
    ("routing_decision", _ROUTING, "action=current"),
    ("intent_classification", _INTENT_CACHED, "(cached)"),
    ("intent_classification", _INTENT_CACHED, "conf=0.92"),
    ("intent_classification", _INTENT_BADCONF, "conf=NaNstr"),
    ("tool_call", _TOOL_CALL, "name=update_person_name"),
    ("tool_result", _TOOL_RESULT_ERR, "error='boom'"),
    ("tool_result", _TOOL_RESULT_OK, "status=ok"),
    ("memory_write", _MEMORY, "role=user"),
    ("state_write", _STATE, "current_person='jagan'"),
    ("state_write", _STATE_EMPTY, "visible=none"),
    ("tts_out", _TTS_STREAM, "(stream)"),
    ("tts_out", _TTS_PLAIN, "purpose=reply"),
    ("session_lifecycle", _LIFECYCLE, "lifecycle=open"),
])
def test_summarize_payload_per_type(replay_cli, event_type, payload, expected):
    out = replay_cli._summarize_payload(event_type, 1, payload)
    assert expected in out

def test_summarize_payload_dispatch_failure_falls_back(replay_cli):
    """from_json_dict raises (missing key) → obj None → JSON fallback (243-246)."""
    out = replay_cli._summarize_payload("audio_in", 1, {"speech_secs": 1.0})
    assert out == json.dumps({"speech_secs": 1.0}, default=str, sort_keys=True)

def test_summarize_payload_unknown_event_type_no_class_falls_back(replay_cli):
    """cls is None (event_type not in dispatch) → JSON fallback (243-246)."""
    out = replay_cli._summarize_payload("no_such_event", 1, {"a": 1})
    assert out == json.dumps({"a": 1}, default=str, sort_keys=True)

def test_summarize_payload_known_class_unhandled_type_final_fallback(
    replay_cli, monkeypatch,
):
    """obj deserializes fine but event_type isn't in the if-chain → the
    defensive final fallback at line 316. Reached by pointing a made-up
    event_type at a real payload class via the dispatch table."""
    audio_cls = replay_cli._PAYLOAD_CLASSES[("audio_in", 1)]
    monkeypatch.setitem(replay_cli._PAYLOAD_CLASSES, ("mystery", 1), audio_cls)
    out = replay_cli._summarize_payload("mystery", 1, _AUDIO_IN)
    # Line 316 wraps the JSON dump in _truncate (60-char cap); _AUDIO_IN's
    # dump is longer, so it comes back truncated with the "..." suffix.
    assert out == replay_cli._truncate(
        json.dumps(_AUDIO_IN, default=str, sort_keys=True)
    )
    assert out.endswith("...")

# ══════════════════════════════════════════════════════════════════════════
# _fmt_ts (324-328)
# ══════════════════════════════════════════════════════════════════════════

def test_fmt_ts_shape(replay_cli):
    out = replay_cli._fmt_ts(1779008461.123)
    # HH:MM:SS.mmm
    assert len(out) == 12 and out[2] == ":" and out[5] == ":" and out[8] == "."

# ══════════════════════════════════════════════════════════════════════════
# _format_event_line (331-361)
# ══════════════════════════════════════════════════════════════════════════

def _event(**over):
    base = {
        "id": 1, "ts": 100.0, "session_id": "jagan_001",
        "room_session_id": "room_x", "event_type": "audio_in",
        "schema_version": 1, "payload_json": json.dumps(_AUDIO_IN),
        "parent_event_id": None,
    }
    base.update(over)
    return base

def test_format_event_line_full(replay_cli):
    line = replay_cli._format_event_line(_event(parent_event_id=7))
    assert "session='jagan_001'" in line
    assert "room='room_x'" in line
    assert "parent=7" in line
    assert "hello there" in line
    assert "└─" not in line  # indent 0

def test_format_event_line_minimal_fields(replay_cli):
    line = replay_cli._format_event_line(
        _event(session_id=None, room_session_id=None, parent_event_id=None)
    )
    assert "session=" not in line
    assert "room=" not in line
    assert "parent=" not in line

def test_format_event_line_indented(replay_cli):
    line = replay_cli._format_event_line(_event(), indent=1)
    assert line.startswith("  └─ ")

@pytest.mark.parametrize("bad_payload", ["{not valid json", 12345])
def test_format_event_line_malformed_payload(replay_cli, bad_payload):
    """Malformed JSON string → JSONDecodeError; non-str → TypeError.
    Both hit the except at 340-341 and fall back to {}."""
    line = replay_cli._format_event_line(_event(payload_json=bad_payload))
    # empty dict summarised → falls into audio_in dispatch failure fallback
    assert isinstance(line, str) and "id=1" in line

def test_format_event_line_empty_payload_json(replay_cli):
    """Falsy payload_json short-circuits to {} without decoding (line 339)."""
    line = replay_cli._format_event_line(_event(payload_json=""))
    assert "id=1" in line

def test_format_event_line_raw_payload(replay_cli):
    line = replay_cli._format_event_line(_event(), raw_payload=True)
    assert "\n" in line
    assert json.dumps(json.loads(json.dumps(_AUDIO_IN)), sort_keys=True) in line

# ══════════════════════════════════════════════════════════════════════════
# _render (364-378)
# ══════════════════════════════════════════════════════════════════════════

def test_render_flat_mode(replay_cli):
    events = [_event(id=1), _event(id=2, parent_event_id=1)]
    lines = list(replay_cli._render(events, tree=False))
    assert len(lines) == 2
    assert all("└─" not in ln for ln in lines)

def test_render_tree_mode_indents_in_window_children(replay_cli):
    events = [
        _event(id=1, parent_event_id=None),          # root
        _event(id=2, parent_event_id=1),             # child in-window → indent
        _event(id=3, parent_event_id=99999,          # orphan → flat
               session_id="ghost"),
    ]
    lines = list(replay_cli._render(events, tree=True))
    assert len(lines) == 3
    assert "└─" not in lines[0]                       # root flat
    assert lines[1].startswith("  └─ ")               # child indented
    ghost = next(ln for ln in lines if "ghost" in ln)
    assert "└─" not in ghost                           # orphan flat

# ══════════════════════════════════════════════════════════════════════════
# _print_header (386-399)
# ══════════════════════════════════════════════════════════════════════════

def test_print_header_all_filters(replay_cli, capsys):
    args = argparse.Namespace(
        db="/tmp/brain.db", session="jagan_001", room="room_1",
        event_type="audio_in", since="1h", limit=50,
    )
    replay_cli._print_header(args, 3)
    out = capsys.readouterr().out
    assert "3 event(s)" in out
    assert "session=jagan_001" in out
    assert "room=room_1" in out
    assert "type=audio_in" in out
    assert "since=1h" in out
    assert "limit=50" in out
    assert "-" * 78 in out

def test_print_header_no_filters(replay_cli, capsys):
    args = argparse.Namespace(
        db="/tmp/brain.db", session=None, room=None, event_type=None,
        since=None, limit=0,
    )
    replay_cli._print_header(args, 0)
    out = capsys.readouterr().out
    assert "0 event(s)" in out
    assert "session=" not in out
    assert "room=" not in out
    assert "type=" not in out
    assert "since=" not in out
    assert "limit=" not in out

# ══════════════════════════════════════════════════════════════════════════
# _ensure_utf8_stdout (402-412)
# ══════════════════════════════════════════════════════════════════════════

def test_ensure_utf8_stdout_reconfigures(replay_cli, monkeypatch):
    calls = []

    class _FakeStdout:
        def reconfigure(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setattr(sys, "stdout", _FakeStdout())
    replay_cli._ensure_utf8_stdout()
    monkeypatch.undo()
    assert calls == [{"encoding": "utf-8", "errors": "replace"}]

def test_ensure_utf8_stdout_swallows_attribute_error(replay_cli, monkeypatch):
    class _NoReconfigure:
        pass

    monkeypatch.setattr(sys, "stdout", _NoReconfigure())
    replay_cli._ensure_utf8_stdout()  # must not raise
    monkeypatch.undo()

def test_ensure_utf8_stdout_swallows_os_error(replay_cli, monkeypatch):
    class _RaisingStdout:
        def reconfigure(self, **kwargs):
            raise OSError("stream detached")

    monkeypatch.setattr(sys, "stdout", _RaisingStdout())
    replay_cli._ensure_utf8_stdout()  # must not raise
    monkeypatch.undo()

# ══════════════════════════════════════════════════════════════════════════
# main (415-439) — end-to-end against a tmp DB
# ══════════════════════════════════════════════════════════════════════════

def _full_db(tmp_path: Path) -> Path:
    rows = [
        (1, 100.0, "jagan_001", "room_x", "audio_in", 1,
         json.dumps(_AUDIO_IN), None),
        (2, 200.0, "jagan_001", "room_x", "identity_claim", 1,
         json.dumps(_IDENTITY_CLAIM), 1),
        (3, 300.0, "jagan_001", "room_x", "routing_decision", 1,
         json.dumps(_ROUTING), 2),
        (4, 400.0, "lexi_002", "room_y", "tts_out", 1,
         json.dumps(_TTS_STREAM), None),
    ]
    return _make_db(tmp_path, rows)

def test_main_tree_render(replay_cli, tmp_path, capsys):
    db = _full_db(tmp_path)
    rc = replay_cli.main(["--db", str(db), "--session", "jagan_001",
                          "--limit", "10"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "3 event(s)" in out          # 3 jagan_001 events
    assert "└─" in out                   # tree indentation for chained events
    assert "hello there" in out

def test_main_no_tree_and_raw_payload(replay_cli, tmp_path, capsys):
    db = _full_db(tmp_path)
    rc = replay_cli.main(["--db", str(db), "--no-tree", "--raw-payload"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "4 event(s)" in out
    assert "└─" not in out               # flat mode
    # raw payload dump present (a full JSON object line)
    assert '"audio_hash"' in out

def test_main_with_since_and_type_filters(replay_cli, tmp_path, capsys):
    db = _full_db(tmp_path)
    rc = replay_cli.main(["--db", str(db), "--type", "tts_out",
                          "--since", "1s"])
    assert rc == 0
    out = capsys.readouterr().out
    # ts values are ~100-400 (far in the past) so `--since 1s` (now-1s)
    # filters everything out → 0 events, header still prints.
    assert "0 event(s)" in out
    assert "type=tts_out" in out

def test_main_missing_db_raises_systemexit(replay_cli, tmp_path):
    missing = tmp_path / "nope.db"
    with pytest.raises(SystemExit):
        replay_cli.main(["--db", str(missing)])
