"""core/brain_agent/agents/watchdog.py — WatchdogAgent.

Extracted VERBATIM from core/brain_agent.py (P1.A1 SP-2 Commit 4).
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import asyncio
import datetime
import sqlite3
import time

from core.config import (
    WATCHDOG_INTERVAL,
    WATCHDOG_SILENT_OBS_SPIKE,
    WATCHDOG_UNUSUAL_HOUR_END,
    WATCHDOG_UNUSUAL_HOUR_START,
)


class WatchdogAgent:
    """Monitor system health and behavioural anomalies on a background loop.

    Checks every WATCHDOG_INTERVAL seconds:
    - Silent observation rate spikes
    - Repeated unknown faces at unusual hours
    Camera + API failures are reported via report_* methods called from pipeline.

    Alert types: CAMERA_FAILURE, API_FAILURE, UNUSUAL_FACE, SILENT_OBS_ANOMALY,
                 REPEATED_UNKNOWN
    """

    def __init__(self, brain_db: "BrainDB", faces_conn: sqlite3.Connection):
        self._db         = brain_db
        self._faces_conn = faces_conn

    async def run_loop(self, shutdown: asyncio.Event) -> None:
        while not shutdown.is_set():
            try:
                self._check_silent_obs_anomaly()
                self._check_unusual_repeated_faces()
            except Exception as e:
                print(f"[WatchdogAgent] Check error: {e}")
            try:
                await asyncio.wait_for(shutdown.wait(), timeout=WATCHDOG_INTERVAL)
            except asyncio.TimeoutError:
                pass

    # ── called from pipeline ──────────────────────────────────────────────────

    def report_camera_null_streak(self, streak: int) -> None:
        if not self._db.unresolved_alert_exists("CAMERA_FAILURE"):
            self._db.store_alert(
                "CAMERA_FAILURE", "high",
                f"Camera returned {streak} consecutive null frames — reconnect attempted.",
                {"streak": streak},
            )
            print(f"[WatchdogAgent] CAMERA_FAILURE alert stored (streak={streak})")

    def report_api_failure(self, duration_s: float) -> None:
        if not self._db.unresolved_alert_exists("API_FAILURE"):
            self._db.store_alert(
                "API_FAILURE", "medium",
                f"Together.ai unreachable for {int(duration_s)}s — using offline fallback.",
                {"duration_s": duration_s},
            )
            print(f"[WatchdogAgent] API_FAILURE alert stored ({duration_s:.0f}s)")

    def report_dispute_rename_burst(
        self,
        victim_pid: str,
        victim_name: str,
        victim_person_type: str,
        claimed_name: str,
        block_count: int,
        dispute_started_at: "float | None",
    ) -> None:
        """Record a watchdog alert for a persistent disputed-rename attack.

        Fires when a single disputed session has blocked
        ``DISPUTE_RENAME_BLOCK_THRESHOLD`` rename attempts from the LLM — a strong
        signal that either the speaker really isn't the sensor-matched person
        (impersonation / gallery poisoning) or the tool-call loop is misbehaving.
        Severity escalates to ``"critical"`` when the victim's prior type was
        ``best_friend`` since owner-privilege transfer is the highest blast radius.

        Each burst fires its own alert (no cross-session dedup) — the per-session
        ``disputed_block_alerted`` flag in pipeline.py prevents re-firing within
        the same session.
        """
        severity = "critical" if victim_person_type == "best_friend" else "warning"
        message = (
            f"Session matched as {victim_name!r} (person_type={victim_person_type!r}) "
            f"blocked {block_count} rename attempts to {claimed_name!r}. "
            f"Suggests the current speaker may not be {victim_name}. "
            f"Run `python audit_person.py --id {victim_pid}` then "
            f"`python repair_gallery.py --id {victim_pid}` to inspect and clean "
            f"the gallery; factory-reset if drift is severe."
        )
        metadata = {
            "victim_pid":          victim_pid,
            "victim_name":         victim_name,
            "victim_person_type":  victim_person_type,
            "claimed_name":        claimed_name,
            "block_count":         block_count,
            "dispute_started_at":  dispute_started_at,
        }
        self._db.store_alert("DISPUTE_RENAME_BURST", severity, message, metadata)
        print(
            f"[WatchdogAgent] DISPUTE_RENAME_BURST ({severity}): "
            f"{victim_name} blocked {block_count} attempts → {claimed_name!r}"
        )

    def report_anti_spoof_rejection(
        self,
        track_id: str,
        reason: str,
        score: "float | None",
        person_id: "str | None" = None,
    ) -> None:
        """P0.S1 Phase 3 — record a per-instance anti-spoof rejection.

        Severity="info" because a single rejection is usually a transient
        false negative or one frame in a normal scan; the meaningful signal
        is the burst aggregator (`report_anti_spoof_burst`). Operators
        watching the dashboard see these as fine-grained activity entries.
        """
        self._db.store_alert(
            "ANTI_SPOOF_REJECTION",
            "info",
            f"Anti-spoof rejected face for track={track_id} "
            f"reason={reason} score={score!r} person={person_id!r}",
            {
                "track_id":  track_id,
                "reason":    reason,
                "score":     score,
                "person_id": person_id,
            },
        )

    def report_anti_spoof_burst(
        self,
        track_id: str,
        count: int,
        window_secs: float,
        threshold: int,
        person_id: "str | None" = None,
    ) -> None:
        """P0.S1 Phase 3 + §14b.1 — burst-threshold alert (fires once at the
        exact-equality trigger `count == THRESHOLD`).

        Severity="warning" because a sustained burst suggests an active
        attack — repeated photo/screen presentations against the same
        SORT track. The pipeline-side caller guarantees this fires at
        most once per burst window per track (exact-equality + state
        management on the rejection store).
        """
        message = (
            f"Anti-spoof burst threshold reached for track={track_id}: "
            f"{count} rejection(s) within {window_secs:.0f}s "
            f"(threshold={threshold}). "
            f"Likely active presentation attack — check camera view and "
            f"recent enrollment attempts."
        )
        self._db.store_alert(
            "ANTI_SPOOF_BURST",
            "warning",
            message,
            {
                "track_id":    track_id,
                "count":       count,
                "window_secs": window_secs,
                "threshold":   threshold,
                "person_id":   person_id,
            },
        )
        print(
            f"[WatchdogAgent] ANTI_SPOOF_BURST (warning): "
            f"track={track_id} count={count}/{threshold} in {window_secs:.0f}s"
        )

    def resolve_camera_failure(self) -> None:
        """Call from pipeline when camera reconnects successfully."""
        self._db.resolve_alerts_by_type("CAMERA_FAILURE")

    def resolve_api_failure(self) -> None:
        """Call from pipeline when Together.ai recovers."""
        self._db.resolve_alerts_by_type("API_FAILURE")

    def report_antispoof_disabled(self) -> None:
        """Record a persistent alert when MiniFASNet fails to load."""
        if not self._db.unresolved_alert_exists("ANTISPOOF_DISABLED"):
            self._db.store_alert(
                "ANTISPOOF_DISABLED", "high",
                "Anti-spoofing is DISABLED — photo/screen-replay attacks will succeed. "
                "Install silent-face-anti-spoofing to enable.",
                {},
            )
            print("[WatchdogAgent] ANTISPOOF_DISABLED alert stored")

    def report_disk_threshold(
        self,
        level: int,
        percent_used: float,
        free_bytes: int,
        severity: str,
    ) -> None:
        """Store a disk-space threshold crossing alert.

        alert_type encodes the exact threshold (disk_warning_80, disk_warning_90,
        disk_critical_95) so the dashboard can distinguish them.
        Called from core/disk_monitor.check_disk_thresholds; idempotency is
        managed there via _last_disk_alert_level module state.
        """
        alert_type = f"disk_critical_{level}" if level >= 95 else f"disk_warning_{level}"
        self._db.store_alert(
            alert_type,
            severity,
            f"Disk usage crossed {level}% threshold — {percent_used:.1f}% used, "
            f"{free_bytes // 1_000_000}MB free.",
            {"percent_used": percent_used, "free_bytes_at_alert": free_bytes, "level": level},
        )
        print(f"[WatchdogAgent] {alert_type} alert stored ({percent_used:.1f}% used)")

    def report_heavy_worker_burst(
        self,
        task_name: str,
        crash_count: int,
        window_secs: float,
    ) -> None:
        """Store a heavy-worker pool burst-crash alert (P0.R8 D4).

        Called from ``pipeline._heavy_worker_watchdog_loop`` when the rolling
        crash count for a pool within ``HEAVY_WORKER_RESTART_BURST_WINDOW_SECS``
        exceeds ``HEAVY_WORKER_RESTART_BURST_THRESHOLD``.

        Severity is ``warning`` — heavy-worker degraded is recoverable;
        operator-actionable but not session-blocking. ProcessPoolExecutor
        auto-respawns subprocesses on next submit; recovery happens
        implicitly when the crash rate drops below threshold within the
        rolling window.

        Idempotency: managed by the watchdog loop's per-pool ``_alert_armed``
        flag (one alert per pool per burst event; re-arms on recovery).
        """
        self._db.store_alert(
            f"heavy_worker_burst_{task_name}",
            "warning",
            f"Heavy-worker pool '{task_name}' crashed {crash_count} times in "
            f"the last {window_secs:.0f}s. Pool will auto-respawn but is marked "
            f"degraded. Check logs for crash root cause (CUDA OOM, model file "
            f"corruption, etc.).",
            {
                "task_name": task_name,
                "crash_count": crash_count,
                "window_secs": window_secs,
            },
        )
        print(
            f"[WatchdogAgent] heavy_worker_burst_{task_name} alert stored "
            f"({crash_count} crashes / {window_secs:.0f}s)"
        )

    def report_vram_budget_refusal(
        self,
        task_name: str,
        cumulative_mb: int,
        ceiling_mb: int,
        estimate_mb: int,
    ) -> None:
        """Store a VRAM budget refusal alert (P0.R9 D5).

        Called from ``core.heavy_worker.get_or_create_pool`` on first refusal
        per task_name. Severity ``warning`` — graceful degradation (caller's
        fallback fires; system continues running).

        Q8 (a) RATIFIED: per-pool alert granularity (operator wants to know
        WHICH pool degraded). Alert metadata captures pool name + cumulative
        MB + ceiling MB + estimate MB for operator triage.
        """
        self._db.store_alert(
            f"vram_budget_refusal_{task_name}",
            "warning",
            f"Pool '{task_name}' refused spawn (estimate {estimate_mb}MB + "
            f"cumulative {cumulative_mb}MB > ceiling {ceiling_mb}MB). "
            f"Fallback path active. Tune VRAM_POOL_PRIORITY / VRAM_CEILING_PCT / "
            f"HEAVY_WORKER_VRAM_ESTIMATES_MB at core/config.py + restart to recover.",
            {
                "task_name": task_name,
                "cumulative_mb": cumulative_mb,
                "ceiling_mb": ceiling_mb,
                "estimate_mb": estimate_mb,
            },
        )
        print(
            f"[WatchdogAgent] vram_budget_refusal_{task_name} alert stored "
            f"(estimate={estimate_mb}MB, cumulative={cumulative_mb}MB, "
            f"ceiling={ceiling_mb}MB)"
        )

    def report_audio_device_burst(
        self,
        channel: str,
        failure_count: int,
        window_secs: float,
    ) -> None:
        """Store an audio-device burst alert (P0.R10 D4).

        Called from ``pipeline._audio_device_watchdog_loop`` when the rolling
        failure count for a channel within ``AUDIO_DEVICE_BURST_WINDOW_SECS``
        exceeds ``AUDIO_DEVICE_BURST_THRESHOLD``.

        Q8 (a) RATIFIED severity ``warning``: graceful degradation (caller's
        fallback fires; system continues running). Mirrors P0.R8
        ``report_heavy_worker_burst`` shape.

        Q1 (a) RATIFIED per-channel granularity: channel in {'mic', 'speaker'};
        alert key includes channel name for operator triage clarity.

        Idempotency: managed by the watchdog loop's per-channel
        ``_alert_armed`` flag (one alert per channel per burst event; re-arms
        on recovery).
        """
        self._db.store_alert(
            f"audio_device_burst_{channel}",
            "warning",
            f"Audio device '{channel}' failure burst — {failure_count} failures in "
            f"{window_secs:.0f}s window. Check device connection / driver / "
            f"permissions. Clears when failure rate drops below "
            f"AUDIO_DEVICE_BURST_THRESHOLD.",
            {
                "channel": channel,
                "failure_count": failure_count,
                "window_secs": window_secs,
            },
        )
        print(
            f"[WatchdogAgent] audio_device_burst_{channel} alert stored "
            f"(count={failure_count}, window={window_secs:.0f}s)"
        )

    # ── periodic checks ───────────────────────────────────────────────────────

    def _check_silent_obs_anomaly(self) -> None:
        cutoff = time.time() - WATCHDOG_INTERVAL
        count = self._faces_conn.execute(
            "SELECT COUNT(*) FROM silent_observations WHERE last_seen > ?",
            (cutoff,),
        ).fetchone()[0]
        if count >= WATCHDOG_SILENT_OBS_SPIKE:
            self._db.store_alert(
                "SILENT_OBS_ANOMALY", "low",
                f"{count} new silent observations in the last {int(WATCHDOG_INTERVAL)}s.",
                {"count": count},
            )
            print(f"[WatchdogAgent] SILENT_OBS_ANOMALY: {count} observations in last interval")

    def _check_unusual_repeated_faces(self) -> None:
        now = time.time()
        hour = datetime.datetime.now().hour
        if not (WATCHDOG_UNUSUAL_HOUR_START <= hour <= WATCHDOG_UNUSUAL_HOUR_END):
            return
        cutoff = now - WATCHDOG_INTERVAL * 3   # seen in last 3 check intervals
        rows = self._faces_conn.execute(
            "SELECT id, first_seen, last_seen, frame_count FROM silent_observations "
            "WHERE last_seen > ? AND frame_count >= 10",
            (cutoff,),
        ).fetchall()
        if rows and not self._db.unresolved_alert_exists("UNUSUAL_FACE"):
            self._db.store_alert(
                "UNUSUAL_FACE", "medium",
                f"Unknown face seen at unusual hour ({hour:02d}:xx) with {rows[0][3]} frames.",
                {"hour": hour, "observation_id": rows[0][0]},
            )
            print(f"[WatchdogAgent] UNUSUAL_FACE at hour {hour}")
