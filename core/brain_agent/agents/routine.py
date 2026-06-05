"""core/brain_agent/agents/routine.py — RoutineAgent.

Extracted VERBATIM from core/brain_agent.py (P1.A1 SP-2 Commit 4).
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import statistics

from core.config import (
    MIN_PRESENCE_SESSIONS,
    PRESENCE_DEVIATION_HOURS,
    ROUTINE_STD_THRESHOLD,
)
from core.brain_agent.agents.extraction import Extraction


class RoutineAgent:
    """Detect per-person visit patterns from presence_log.

    Runs synchronously at session end (in a thread executor so it never blocks
    the event loop). Works for ALL persons: best_friend, known, and strangers.

    When a stable pattern is found (std-dev of arrival hours < ROUTINE_STD_THRESHOLD),
    stores it as a fact in the knowledge table via store_knowledge() so the LLM
    context reflects it naturally.
    """

    def __init__(self, brain_db: "BrainDB"):
        self._db = brain_db

    def analyze(self, person_id: str, person_name: str) -> None:
        count = self._db.get_presence_count(person_id)
        if count < MIN_PRESENCE_SESSIONS:
            return
        history = self._db.get_presence_history(person_id, limit=20)
        if not history:
            return

        hours    = [h["hour_of_day"] for h in history]
        durations = [h["duration_s"] for h in history]

        try:
            std_h = statistics.stdev(hours) if len(hours) > 1 else 0.0
        except statistics.StatisticsError:
            return

        if std_h < ROUTINE_STD_THRESHOLD:
            typical_hour = round(statistics.mean(hours))
            avg_dur_min = round(statistics.mean(durations) / 60)
            # Invalidate previous routine facts before storing new ones
            self._db.invalidate(person_name, "typical_arrival_hour", 0)
            self._db.invalidate(person_name, "typical_visit_duration_min", 0)
            # Use store_knowledge() so facts get schema catalog, graph sync, embeddings
            # Session 95 3A.4.5: sync agent, closed attribute set. Both
            # facts describe a specific person's schedule — 'personal' by
            # definition (owner-only). No LLM classify needed.
            self._db.store_knowledge(
                [
                    Extraction(
                        entity=person_name, entity_type="person",
                        attribute="typical_arrival_hour", value=str(typical_hour),
                        confidence=0.80, is_temporal=False, valid_for_hours=None,
                        privacy_level="personal",
                    ),
                    Extraction(
                        entity=person_name, entity_type="person",
                        attribute="typical_visit_duration_min", value=str(avg_dur_min),
                        confidence=0.80, is_temporal=False, valid_for_hours=None,
                        privacy_level="personal",
                    ),
                ],
                turn_id=0,
                person_id=person_id,
                agent="routine_agent",
            )
            print(
                f"[RoutineAgent] {person_name}: typical arrival hour={typical_hour},"
                f" duration≈{avg_dur_min}min (std_h={std_h:.1f})"
            )

    def check_deviation(self, person_id: str, current_hour: int) -> str | None:
        """Return deviation description if current hour is unusual for this person.

        Synchronous SQLite read (<1ms). Called from ProactiveNudgeAgent.
        Returns None if no stable pattern or no deviation.
        """
        history = self._db.get_presence_history(person_id, limit=20)
        if len(history) < MIN_PRESENCE_SESSIONS:
            return None
        hours = [h["hour_of_day"] for h in history]
        try:
            mean_h = statistics.mean(hours)
            std_h  = statistics.stdev(hours) if len(hours) > 1 else 0.0
        except statistics.StatisticsError:
            return None
        if std_h >= ROUTINE_STD_THRESHOLD:
            return None  # pattern not stable enough
        deviation = abs(current_hour - mean_h)
        if deviation >= PRESENCE_DEVIATION_HOURS:
            typical = f"{int(mean_h):02d}:00"
            return f"usually here around {typical} but visiting at {current_hour:02d}:00"
        return None
