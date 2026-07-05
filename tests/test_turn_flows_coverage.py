"""100% coverage for flows.companion.turn_flows.session_end_notify — the
identity-disputed skip branch (P1.A1 SP-7b.2). Part of the coverage-to-100
campaign (see COVERAGE.md)."""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from flows.companion.turn_flows import session_end_notify

def test_disputed_session_skips_log_turn_and_logs(capsys):
    # _is_disputed_session=True -> the `if db and not disputed` branch is
    # False, the `elif disputed` branch prints the skip message (line 90).
    session_end_notify(
        db=None, person_id="stranger_x", text="hi", response="hey",
        _is_disputed_session=True, _room_sid=None,
    )
    out = capsys.readouterr().out
    assert "Skipping log_turn for disputed session stranger_x" in out

def test_no_db_and_not_disputed_is_silent_noop(capsys):
    # db falsy AND not disputed -> neither branch runs; no output, no error.
    session_end_notify(
        db=None, person_id="p1", text="hi", response="hey",
        _is_disputed_session=False, _room_sid=None,
    )
    assert capsys.readouterr().out == ""
