"""Covers RoutineAgent edge branches: empty-history early return in analyze()
and the unstable-pattern return in check_deviation(). The StatisticsError
handlers are pragma'd (defensive: guarded inputs cannot raise). Part of the
coverage-to-100 campaign."""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from unittest.mock import MagicMock

from core.brain_agent.agents.routine import RoutineAgent

def _db(count, history):
    db = MagicMock()
    db.get_presence_count.return_value = count
    db.get_presence_history.return_value = history
    return db

def test_analyze_returns_early_on_empty_history():
    # count clears the min-sessions gate but history is empty -> line 41 return
    db = _db(5, [])
    RoutineAgent(db).analyze("p1", "Alice")
    db.store_knowledge.assert_not_called()

def test_analyze_stores_routine_on_stable_pattern():
    # 5 sessions clustered around the same hour -> stable -> store_knowledge fires
    hist = [{"hour_of_day": h, "duration_s": 3600} for h in [9, 9, 10, 9, 10]]
    db = _db(5, hist)
    RoutineAgent(db).analyze("p1", "Alice")
    assert db.store_knowledge.called

def test_check_deviation_none_when_pattern_unstable():
    # widely varied hours -> std_h >= threshold -> line 101 return None
    hist = [{"hour_of_day": h, "duration_s": 600} for h in [1, 8, 14, 20, 23]]
    assert RoutineAgent(_db(5, hist)).check_deviation("p1", current_hour=12) is None

def test_check_deviation_none_below_min_sessions():
    hist = [{"hour_of_day": 9, "duration_s": 600}]  # < MIN_PRESENCE_SESSIONS
    assert RoutineAgent(_db(1, hist)).check_deviation("p1", current_hour=9) is None

def test_check_deviation_reports_unusual_hour():
    hist = [{"hour_of_day": 9, "duration_s": 600} for _ in range(5)]  # stable ~09:00
    out = RoutineAgent(_db(5, hist)).check_deviation("p1", current_hour=15)
    assert out is not None and "09:00" in out
