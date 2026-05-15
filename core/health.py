"""
System health snapshot and log formatting.
Wave 5 / Item 19 — observability for production operations.
"""
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class HealthSnapshot:
    timestamp: float
    active_sessions: int
    sessions_by_type: "dict[str, int]"
    persons_count: int
    total_face_embeddings: int
    knowledge_active_rows: int
    shadow_persons_count: int
    classifier_scenarios_active: int
    classifier_scenarios_quarantined: int
    cloud_state: str
    active_disputes: int
    unresolved_watchdog_alerts: int
    last_dream_run_seconds_ago: "float | None"
    thin_voice_galleries: "list[tuple[str, int]]"  # [(person_id, count)] for known persons with voice_n < 5


def gather_health_snapshot(
    db: Any,
    brain_orchestrator: Any,
    active_sessions: dict,
    cloud_state: Any,
    last_dream_run_at: "float | None",
) -> HealthSnapshot:
    """Gather all metrics in one pass. Each query is a fast SELECT COUNT(*).
    Total wall-clock budget: <100ms. Run in executor — never on the event loop.
    """
    now = time.time()

    # Sessions by type
    by_type: dict[str, int] = {"best_friend": 0, "known": 0, "stranger": 0, "disputed": 0}
    for s in active_sessions.values():
        pt = s.get("person_type", "stranger")
        by_type[pt] = by_type.get(pt, 0) + 1

    # Active disputes are just disputed sessions
    disputes = by_type.get("disputed", 0)

    # faces.db counts
    try:
        persons_count = db._conn.execute("SELECT COUNT(*) FROM persons").fetchone()[0]
        embed_count   = db._conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
        thin = db._conn.execute("""
            SELECT p.id, COUNT(v.person_id)
            FROM persons p
            LEFT JOIN voice_embeddings v ON p.id = v.person_id
            WHERE p.type IN ('known', 'best_friend')
            GROUP BY p.id
            HAVING COUNT(v.person_id) < 5
        """).fetchall()
    except Exception:
        persons_count = -1
        embed_count   = -1
        thin          = []

    # brain.db counts
    try:
        bdb = brain_orchestrator._brain_db._conn
        knowledge_active = bdb.execute(
            "SELECT COUNT(*) FROM knowledge WHERE invalidated_at IS NULL"
        ).fetchone()[0]
        shadow_count = bdb.execute(
            "SELECT COUNT(*) FROM shadow_persons WHERE enrollment_status != 'confirmed'"
        ).fetchone()[0]
        watchdog_unresolved = bdb.execute(
            "SELECT COUNT(*) FROM watchdog_alerts WHERE resolved = 0"
        ).fetchone()[0]
    except Exception:
        knowledge_active    = -1
        shadow_count        = -1
        watchdog_unresolved = -1

    # classifier_scenarios.db counts — import the module-level singleton lazily
    try:
        from core import classifier_graph as _cg
        cdb_inst = _cg._classifier_db
        if cdb_inst is not None:
            cdb = cdb_inst._conn
            scen_active = cdb.execute(
                "SELECT COUNT(*) FROM scenarios WHERE active = 1"
            ).fetchone()[0]
            scen_quar = cdb.execute(
                "SELECT COUNT(*) FROM scenarios WHERE active = 0"
            ).fetchone()[0]
        else:
            scen_active, scen_quar = 0, 0
    except Exception:
        scen_active, scen_quar = -1, -1

    return HealthSnapshot(
        timestamp=now,
        active_sessions=len(active_sessions),
        sessions_by_type=by_type,
        persons_count=persons_count,
        total_face_embeddings=embed_count,
        knowledge_active_rows=knowledge_active,
        shadow_persons_count=shadow_count,
        classifier_scenarios_active=scen_active,
        classifier_scenarios_quarantined=scen_quar,
        cloud_state=(str(cloud_state.name) if hasattr(cloud_state, "name") else str(cloud_state)),
        active_disputes=disputes,
        unresolved_watchdog_alerts=watchdog_unresolved,
        last_dream_run_seconds_ago=((now - last_dream_run_at) if last_dream_run_at is not None else None),
        thin_voice_galleries=thin,
    )


def format_health_line(s: HealthSnapshot) -> str:
    """One-line system pulse. Target: under 200 chars."""
    from datetime import datetime

    time_str = datetime.fromtimestamp(s.timestamp).strftime("%H:%M")

    parts: list[str] = []
    if s.sessions_by_type.get("best_friend", 0):
        parts.append(f"{s.sessions_by_type['best_friend']}bf")
    if s.sessions_by_type.get("known", 0):
        parts.append(f"{s.sessions_by_type['known']}known")
    if s.sessions_by_type.get("stranger", 0):
        parts.append(f"{s.sessions_by_type['stranger']}stranger")
    if s.sessions_by_type.get("disputed", 0):
        parts.append(f"{s.sessions_by_type['disputed']}disputed")
    sess_str = f"{s.active_sessions}({','.join(parts)})" if parts else str(s.active_sessions)

    if s.last_dream_run_seconds_ago is None:
        dream_str = "never"
    elif s.last_dream_run_seconds_ago < 60:
        dream_str = f"{int(s.last_dream_run_seconds_ago)}s_ago"
    elif s.last_dream_run_seconds_ago < 3600:
        dream_str = f"{int(s.last_dream_run_seconds_ago / 60)}m_ago"
    else:
        dream_str = f"{int(s.last_dream_run_seconds_ago / 3600)}h_ago"

    return (
        f"[Health] {time_str} | sessions={sess_str} | "
        f"faces={s.persons_count}({s.total_face_embeddings}emb) | "
        f"knowledge={s.knowledge_active_rows}({s.shadow_persons_count}shadow) | "
        f"classifier={s.classifier_scenarios_active}act,{s.classifier_scenarios_quarantined}quar | "
        f"cloud={s.cloud_state} | disputes={s.active_disputes} | "
        f"alerts={s.unresolved_watchdog_alerts} | dream={dream_str}"
    )


def format_health_alerts(s: HealthSnapshot, brain_orchestrator: Any) -> "list[str]":
    """Sub-lines for issues the operator should investigate. Empty list = healthy."""
    alerts: list[str] = []

    if s.active_disputes > 0:
        alerts.append(
            f"[Health-Alert] {s.active_disputes} dispute(s) active — investigate via dashboard"
        )

    if s.unresolved_watchdog_alerts > 0:
        try:
            recent = brain_orchestrator._brain_db._conn.execute(
                """SELECT alert_type, created_at FROM watchdog_alerts
                   WHERE resolved = 0
                   ORDER BY created_at DESC LIMIT 5"""
            ).fetchall()
            details = ", ".join(
                f"{t} ({_age_str(time.time() - ts)})" for t, ts in recent
            )
            alerts.append(
                f"[Health-Alert] {s.unresolved_watchdog_alerts} unresolved watchdog alerts: {details}"
            )
        except Exception:
            alerts.append(
                f"[Health-Alert] {s.unresolved_watchdog_alerts} unresolved watchdog alerts"
            )

    if s.thin_voice_galleries:
        from core.config import HEALTH_THIN_VOICE_MAX
        for pid, n in s.thin_voice_galleries[:HEALTH_THIN_VOICE_MAX]:
            alerts.append(f"[Health-Alert] Voice gallery thin: {pid} at {n}/5 samples")

    return alerts


def _age_str(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        return f"{int(seconds / 60)}m"
    if seconds < 86400:
        return f"{int(seconds / 3600)}h"
    return f"{int(seconds / 86400)}d"
