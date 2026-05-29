"""
Tests for core/health.py — Wave 5 / Item 19.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

import time
import types
import pytest
from unittest.mock import MagicMock, patch

from core.health import (
    HealthSnapshot,
    gather_health_snapshot,
    format_health_line,
    format_health_alerts,
)


def _make_snapshot(**overrides):
    defaults = dict(
        timestamp=time.time(),
        active_sessions=2,
        sessions_by_type={"best_friend": 1, "known": 1, "stranger": 0, "disputed": 0},
        persons_count=3,
        total_face_embeddings=45,
        knowledge_active_rows=12,
        shadow_persons_count=2,
        classifier_scenarios_active=5,
        classifier_scenarios_quarantined=1,
        cloud_state="ONLINE",
        active_disputes=0,
        unresolved_watchdog_alerts=0,
        last_dream_run_seconds_ago=300.0,
        thin_voice_galleries=[],
    )
    defaults.update(overrides)
    return HealthSnapshot(**defaults)


class TestGatherHealthSnapshot:
    def test_returns_all_required_fields(self, tmp_path):
        """gather_health_snapshot returns a HealthSnapshot with all required fields."""
        import sqlite3

        # Minimal fake db with _conn
        db_path = tmp_path / "faces.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE persons (id TEXT, type TEXT)")
        conn.execute("CREATE TABLE embeddings (id TEXT)")
        conn.execute(
            "CREATE TABLE voice_embeddings (person_id TEXT, id INTEGER PRIMARY KEY)"
        )
        conn.commit()

        fake_db = MagicMock()
        fake_db._conn = conn

        # Minimal fake brain orchestrator
        brain_db_conn = sqlite3.connect(str(tmp_path / "brain.db"))
        brain_db_conn.execute(
            "CREATE TABLE knowledge (id INTEGER PRIMARY KEY, invalidated_at TEXT)"
        )
        brain_db_conn.execute(
            "CREATE TABLE shadow_persons (id TEXT, enrollment_status TEXT)"
        )
        brain_db_conn.execute(
            "CREATE TABLE watchdog_alerts (id INTEGER PRIMARY KEY, resolved INTEGER DEFAULT 0)"
        )
        brain_db_conn.commit()

        fake_brain_db = MagicMock()
        fake_brain_db._conn = brain_db_conn

        fake_orchestrator = MagicMock()
        fake_orchestrator._brain_db = fake_brain_db

        with patch("core.classifier_graph._classifier_db", None):
            snap = gather_health_snapshot(
                db=fake_db,
                brain_orchestrator=fake_orchestrator,
                active_sessions=[],
                cloud_state="ONLINE",
                last_dream_run_at=None,
            )

        assert isinstance(snap, HealthSnapshot)
        assert snap.active_sessions == 0
        assert snap.cloud_state == "ONLINE"
        assert snap.last_dream_run_seconds_ago is None
        conn.close()
        brain_db_conn.close()

    def test_handles_session_snapshot_list_from_session_store(self, tmp_path):
        """P0.6.6 fix: caller now passes _session_store.peek_all_snapshots()
        (list/tuple of SessionSnapshot dataclasses), not a dict.  Live boot
        symptom (2026-05-16): `AttributeError("'tuple' object has no
        attribute 'values'")` repeating every 5 minutes from health emit.

        gather_health_snapshot must iterate the list directly and
        attribute-access `person_type` (not `.get()`)."""
        import asyncio
        import sqlite3
        from core.session_state import SessionStore

        # Real SessionStore with two snapshots of different types.
        store = SessionStore()
        asyncio.run(store.open_session("jagan_001", "Jagan", "best_friend",
                                       "face", now=time.time()))
        asyncio.run(store.open_session("alice_002", "Alice", "known",
                                       "face", now=time.time()))
        snaps = store.peek_all_snapshots()
        # Sanity guard the regression: peek_all_snapshots returns a non-dict.
        assert not hasattr(snaps, "values")

        # Minimal fake DBs (same shape as test_returns_all_required_fields).
        conn = sqlite3.connect(str(tmp_path / "faces.db"))
        conn.execute("CREATE TABLE persons (id TEXT, type TEXT)")
        conn.execute("CREATE TABLE embeddings (id TEXT)")
        conn.execute("CREATE TABLE voice_embeddings (person_id TEXT, id INTEGER PRIMARY KEY)")
        conn.commit()
        fake_db = MagicMock(); fake_db._conn = conn
        brain_db_conn = sqlite3.connect(str(tmp_path / "brain.db"))
        brain_db_conn.execute("CREATE TABLE knowledge (id INTEGER PRIMARY KEY, invalidated_at TEXT)")
        brain_db_conn.execute("CREATE TABLE shadow_persons (id TEXT, enrollment_status TEXT)")
        brain_db_conn.execute("CREATE TABLE watchdog_alerts (id INTEGER PRIMARY KEY, resolved INTEGER DEFAULT 0)")
        brain_db_conn.commit()
        fake_brain_db = MagicMock(); fake_brain_db._conn = brain_db_conn
        fake_orchestrator = MagicMock(); fake_orchestrator._brain_db = fake_brain_db

        with patch("core.classifier_graph._classifier_db", None):
            snap = gather_health_snapshot(
                db=fake_db,
                brain_orchestrator=fake_orchestrator,
                active_sessions=snaps,
                cloud_state="ONLINE",
                last_dream_run_at=None,
            )

        # 2 active sessions, one of each type — proves attribute access works.
        assert snap.active_sessions == 2
        assert snap.sessions_by_type["best_friend"] == 1
        assert snap.sessions_by_type["known"] == 1
        assert snap.sessions_by_type["stranger"] == 0
        conn.close()
        brain_db_conn.close()


class TestFormatHealthLine:
    def test_under_200_chars(self):
        snap = _make_snapshot()
        line = format_health_line(snap)
        assert line.startswith("[Health]")
        assert len(line) <= 200

    def test_contains_key_fields(self):
        snap = _make_snapshot(persons_count=7, total_face_embeddings=88, cloud_state="SICK")
        line = format_health_line(snap)
        assert "faces=7" in line
        assert "88emb" in line
        assert "cloud=SICK" in line

    def test_dream_never_when_none(self):
        snap = _make_snapshot(last_dream_run_seconds_ago=None)
        line = format_health_line(snap)
        assert "dream=never" in line

    def test_dream_minutes_ago(self):
        snap = _make_snapshot(last_dream_run_seconds_ago=120.0)
        line = format_health_line(snap)
        assert "2m_ago" in line


class TestFormatHealthAlerts:
    def test_empty_list_when_healthy(self):
        snap = _make_snapshot(active_disputes=0, unresolved_watchdog_alerts=0)
        fake_orch = MagicMock()
        alerts = format_health_alerts(snap, fake_orch)
        assert alerts == []

    def test_lists_active_disputes_when_present(self):
        snap = _make_snapshot(active_disputes=2)
        fake_orch = MagicMock()
        alerts = format_health_alerts(snap, fake_orch)
        assert any("dispute" in a.lower() for a in alerts)

    def test_caps_thin_voice_gallery_alerts(self):
        """At most HEALTH_THIN_VOICE_MAX thin-gallery lines are emitted."""
        thin = [(f"pid_{i}", i) for i in range(10)]
        snap = _make_snapshot(thin_voice_galleries=thin)
        fake_orch = MagicMock()
        from core.config import HEALTH_THIN_VOICE_MAX
        alerts = format_health_alerts(snap, fake_orch)
        thin_alerts = [a for a in alerts if "Voice gallery thin" in a]
        assert len(thin_alerts) <= HEALTH_THIN_VOICE_MAX


# ══════════════════════════════════════════════════════════════════════════
# P0.0.7 D8.5 — event_log subsystem health surfacing
# ══════════════════════════════════════════════════════════════════════════


class TestEventLogHealthIntegration:
    """5 tests verifying event_log counters surface through HealthSnapshot
    + format_health_line + format_health_alerts (D5 circular-dependency
    guard: counters are the observability signal, NOT a self-emitting
    event_log_dropped event)."""

    def test_a_health_snapshot_carries_event_log_fields(self):
        """D8.1: HealthSnapshot has event_log_drops + event_log_emit_failures
        as named fields with int defaults of 0."""
        from dataclasses import fields
        field_names = {f.name for f in fields(HealthSnapshot)}
        assert "event_log_drops" in field_names, (
            "D8.1 violation: HealthSnapshot missing event_log_drops field."
        )
        assert "event_log_emit_failures" in field_names, (
            "D8.1 violation: HealthSnapshot missing event_log_emit_failures field."
        )
        # Defaults — a snapshot without explicit overrides should land at 0.
        snap = _make_snapshot()
        assert snap.event_log_drops == 0
        assert snap.event_log_emit_failures == 0

    def test_b_format_health_line_omits_event_log_when_both_zero(self):
        """D8.2: steady-state runs (both counters 0) keep the line clean —
        no `event_log_drops=0` or `event_log_emit_failures=0` chatter."""
        snap = _make_snapshot(event_log_drops=0, event_log_emit_failures=0)
        line = format_health_line(snap)
        assert "event_log_drops" not in line, (
            f"D8.2 violation: zero-drop counter leaked into line: {line!r}"
        )
        assert "event_log_emit_failures" not in line, (
            f"D8.2 violation: zero-emit-failure counter leaked into line: {line!r}"
        )

    def test_c_format_health_line_includes_event_log_when_nonzero(self):
        """D8.2: non-zero counters surface in the line with their names
        as grep targets — operators look for the specific counter."""
        # Only drops > 0
        snap = _make_snapshot(event_log_drops=5, event_log_emit_failures=0)
        line = format_health_line(snap)
        assert "event_log_drops=5" in line, (
            f"D8.2: non-zero drops should appear in line; got {line!r}"
        )
        assert "event_log_emit_failures" not in line, (
            f"D8.2: zero emit_failures should be omitted even when drops>0; "
            f"got {line!r}"
        )

        # Both > 0
        snap = _make_snapshot(event_log_drops=3, event_log_emit_failures=7)
        line = format_health_line(snap)
        assert "event_log_drops=3" in line
        assert "event_log_emit_failures=7" in line

    def test_d_format_health_alerts_fires_on_emit_failures(self):
        """D8.3: format_health_alerts emits a [Health-Alert] line for
        EITHER counter being non-zero. Alert text names the specific
        counter so operators investigate the right surface."""
        fake_orch = MagicMock()

        # Drops only
        snap = _make_snapshot(event_log_drops=5, event_log_emit_failures=0)
        alerts = format_health_alerts(snap, fake_orch)
        drop_alerts = [a for a in alerts if "event_log_drops" in a]
        assert len(drop_alerts) == 1, (
            f"D8.3: expected 1 drop alert, got {len(drop_alerts)}: {alerts}"
        )
        assert "event_log_drops=5" in drop_alerts[0]
        assert "writer task" in drop_alerts[0] or "queue" in drop_alerts[0], (
            "D8.3: drop alert should mention the writer-task / bounded-queue "
            "remediation pointer."
        )

        # Emit failures only
        snap = _make_snapshot(event_log_drops=0, event_log_emit_failures=2)
        alerts = format_health_alerts(snap, fake_orch)
        emit_alerts = [a for a in alerts if "event_log_emit_failures" in a]
        assert len(emit_alerts) == 1, (
            f"D8.3: expected 1 emit-failure alert, got {len(emit_alerts)}: {alerts}"
        )
        assert "event_log_emit_failures=2" in emit_alerts[0]
        assert "[EventLog] WARN" in emit_alerts[0], (
            "D8.3: emit-failure alert should point at the [EventLog] WARN "
            "log lines for the failure-type root cause."
        )

        # Both — two alerts
        snap = _make_snapshot(event_log_drops=1, event_log_emit_failures=1)
        alerts = format_health_alerts(snap, fake_orch)
        evlog_alerts = [a for a in alerts if "event_log_" in a]
        assert len(evlog_alerts) == 2, (
            f"D8.3: expected 2 event_log alerts when both counters > 0, "
            f"got {len(evlog_alerts)}: {alerts}"
        )

        # Zero — no alerts at all
        snap = _make_snapshot(event_log_drops=0, event_log_emit_failures=0)
        alerts = format_health_alerts(snap, fake_orch)
        evlog_alerts = [a for a in alerts if "event_log_" in a]
        assert not evlog_alerts, (
            f"D8.3: no event_log alerts should fire when both counters = 0; "
            f"got: {evlog_alerts}"
        )

    def test_e_gather_snapshot_does_not_block_on_writer_task(self, tmp_path):
        """D8.5: gather_health_snapshot must return promptly even when
        the event_log writer task is busy or absent. The lazy-import +
        counter-only-read path (no DB hit, no async wait) keeps the
        health log on its 5-minute cadence regardless of event-log state.

        Test approach: measure wall-clock time of gather_health_snapshot
        under the same conditions as the production cadence — no event_log
        writer running, counter values arbitrary. Budget: <100ms.
        """
        import sqlite3

        # Minimal fake db with _conn (matches existing test fixture shape).
        db_path = tmp_path / "faces.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE persons (id TEXT, type TEXT)")
        conn.execute("CREATE TABLE embeddings (id TEXT)")
        conn.execute("CREATE TABLE voice_embeddings (person_id TEXT, id INTEGER PRIMARY KEY)")
        conn.commit()
        fake_db = MagicMock()
        fake_db._conn = conn

        # Minimal fake orchestrator
        fake_orch = MagicMock()
        brain_conn = sqlite3.connect(":memory:")
        brain_conn.execute(
            "CREATE TABLE knowledge (id INTEGER, invalidated_at REAL)"
        )
        brain_conn.execute(
            "CREATE TABLE shadow_persons (id INTEGER, enrollment_status TEXT)"
        )
        brain_conn.execute(
            "CREATE TABLE watchdog_alerts (id INTEGER, resolved INTEGER)"
        )
        fake_orch._brain_db._conn = brain_conn

        # Inject non-zero counters into the event_log producer so the
        # gather path actually reads them (rather than catching ImportError).
        from core.event_log import producer as _producer
        original_drops = _producer._drop_count
        original_failures = _producer._safe_emit_failure_count
        _producer._drop_count = 42
        _producer._safe_emit_failure_count = 7

        try:
            t0 = time.perf_counter()
            snap = gather_health_snapshot(
                db=fake_db,
                brain_orchestrator=fake_orch,
                active_sessions=[],
                cloud_state="ONLINE",
                last_dream_run_at=None,
            )
            elapsed = time.perf_counter() - t0
        finally:
            _producer._drop_count = original_drops
            _producer._safe_emit_failure_count = original_failures
            conn.close()
            brain_conn.close()

        # Counters reached the snapshot.
        assert snap.event_log_drops == 42, (
            f"D8.5: gather didn't pull current drop count; got {snap.event_log_drops}"
        )
        assert snap.event_log_emit_failures == 7, (
            f"D8.5: gather didn't pull current emit-failure count; "
            f"got {snap.event_log_emit_failures}"
        )

        # Wall-clock budget: <100ms per Wave 5 / Item 19 spec.
        assert elapsed < 0.100, (
            f"D8.5 perf gate: gather_health_snapshot took {elapsed * 1000:.1f}ms "
            f"(budget: 100ms). The event_log counter read should not block on "
            f"the writer task — verify no synchronous await / DB query was "
            f"introduced by the integration."
        )
