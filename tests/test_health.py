"""
Tests for core/health.py — Wave 5 / Item 19.
"""
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
                active_sessions={},
                cloud_state="ONLINE",
                last_dream_run_at=None,
            )

        assert isinstance(snap, HealthSnapshot)
        assert snap.active_sessions == 0
        assert snap.cloud_state == "ONLINE"
        assert snap.last_dream_run_seconds_ago is None
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
