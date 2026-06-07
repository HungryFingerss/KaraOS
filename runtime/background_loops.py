# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors
"""runtime/background_loops.py — the background-task engine surface (P1.A1 SP-6.4).

The run()-spawned background loops (_dream_loop idle pruning/backup + _health_log_loop
health/disk pulse) + the conversation_turn-spawned cloud-recovery loop (_cloud_retry_loop)
+ the monitoring helper (_emit_health), relocated VERBATIM from pipeline.py modulo the
bare->_wiring._shutdown_event rewiring (_shutdown_event WIRE-d to runtime.wiring this slice).

1 move-with global: _last_dream_run_at (dream-completion timestamp — written by _dream_loop,
read by _emit_health; move-set-only, no cross-module-set). Engine layer: runtime -> core;
imports runtime.wiring + core.*; never pipeline. pipeline.py re-exports the 3 spawned loops
(_cloud_retry_loop/_dream_loop/_health_log_loop) so run() + conversation_turn + the test suite
stay byte-identical; _emit_health is move-set-internal (NOT re-exported).
"""
from __future__ import annotations

import asyncio
import core.config as config
import runtime.wiring as _wiring
import time
from core.brain import ping_together
from core.config import (
    CLOUD_RETRY_INTERVAL, DREAM_COOLDOWN, DREAM_IDLE_MINUTES, DREAM_MAX_INTERVAL, STRANGER_VOICE_TTL_DAYS,
)
from runtime.log_capture import _check_terminal_output_size_cap, _prune_old_terminal_archives
from runtime.state_enums import CloudState
from runtime.wiring import _voice_gallery_store


_last_dream_run_at:   "float | None"    = None   # Wave 5 Item 19: timestamp of last dream() completion
async def _cloud_retry_loop() -> None:
    """
    Background task: runs for the full session lifetime once spawned.
    Pings Together.ai every CLOUD_RETRY_INTERVAL seconds while SICK or OFFLINE.
    Skips pinging when ONLINE — keeps the loop alive for any future outage.
    Sets _cloud_recovered flag on recovery.
    """
    while not _wiring._shutdown_event.is_set():
        try:
            await asyncio.wait_for(_wiring._shutdown_event.wait(), timeout=CLOUD_RETRY_INTERVAL)
            return  # shutdown requested
        except asyncio.TimeoutError:
            pass

        if _wiring._pipeline_state_store.peek_cloud_state() == CloudState.ONLINE:
            continue  # ONLINE — skip ping, keep loop alive for next potential outage

        print("[Pipeline] Retrying Together.ai connection...")
        available = await ping_together()
        if available:
            print("[Pipeline] Together.ai reconnected!")
            asyncio.create_task(_wiring._pipeline_state_store.transition_to_online())
            if _wiring._brain_orchestrator:
                _wiring._brain_orchestrator.report_api_recovered()
        elif _wiring._pipeline_state_store.peek_cloud_failed_at() and _wiring._brain_orchestrator:
            _wiring._brain_orchestrator.report_api_failure(
                time.monotonic() - _wiring._pipeline_state_store.peek_cloud_failed_at()
            )
async def _dream_loop(db: "FaceDB") -> None:
    """Pattern 4: autoDream — consolidate memory during idle periods.

    Waits for DREAM_IDLE_MINUTES of idle (no active person), then calls
    brain_orchestrator.dream() to write decay back to stored knowledge and
    tidy schema synonyms. Runs at most once per DREAM_COOLDOWN seconds.
    Wakes immediately on shutdown.
    """
    global _last_dream_run_at
    # Initial delay: let the system settle after startup
    try:
        await asyncio.wait_for(_wiring._shutdown_event.wait(), timeout=DREAM_IDLE_MINUTES * 60)
        return  # shutdown during initial wait
    except asyncio.TimeoutError:
        pass

    _last_dream_at = 0.0
    while not _wiring._shutdown_event.is_set():
        now = time.time()
        cooldown_elapsed = (now - _last_dream_at) >= DREAM_COOLDOWN
        idle_trigger     = not _wiring._session_store.peek_all_snapshots() and cooldown_elapsed
        force_trigger    = (now - _last_dream_at) >= DREAM_MAX_INTERVAL
        if idle_trigger or force_trigger:
            if force_trigger and _wiring._session_store.peek_all_snapshots():
                print("[Dream] Force trigger — system has been busy, running dream during active session")
            idle_mins = (now - _last_dream_at) / 60 if _last_dream_at > 0 else 0
            print(f"[Dream] Starting consolidation cycle (idle={idle_mins:.1f}min, force={force_trigger})")
            await _wiring._brain_orchestrator.dream()
            # Stranger TTL cleanup — Wave 3 Item 15: rebuild_faiss_async keeps the index
            # swap off the critical path. recognize() continues on the OLD index while
            # the new one builds in a worker thread; no conversation latency spike.
            loop = asyncio.get_event_loop()
            pruned_ids = await db.prune_old_strangers_async(loop)
            if pruned_ids:
                _wiring._brain_orchestrator.prune_brain_data(pruned_ids)
                print(f"[Dream] Strangers pruned: {len(pruned_ids)}")
            # Voice-profile hygiene: strangers whose voice never matured become
            # false-positive sources; evict the in-memory cache FIRST so concurrent
            # voice_mod.identify() calls can't keep matching against the stale mean,
            # then delete the rows from SQLite. Finding J — ordering matters even
            # for microsecond windows.
            stale_ids = db.find_stale_stranger_voice_ids(STRANGER_VOICE_TTL_DAYS)
            if stale_ids:
                for _pid in stale_ids:
                    await _voice_gallery_store.pop_gallery(_pid)
                # Pass the pre-computed ids so prune doesn't re-run the SELECT.
                voice_pruned_ids = db.prune_stale_stranger_voice(
                    STRANGER_VOICE_TTL_DAYS, ids=stale_ids,
                )
                print(f"[Dream] Stale stranger voice rows pruned: {len(voice_pruned_ids)}")
            # Obs 1 (2026-04-20): opportunistic voice-gallery reconciliation.
            # Defense-in-depth for out-of-process deletes (dashboard, CLI) that clear
            # ``voice_embeddings`` rows but can't invalidate the pipeline's in-memory
            # cache. Dream runs during idle windows so a full scan is effectively
            # free. Divergence → reload embeddings for the affected pids too, so
            # voice_mod.identify() can't keep matching against a vanished mean.
            _fresh_sizes = db.load_voice_profile_sizes()
            _reconciled = await _voice_gallery_store.reconcile(_fresh_sizes, db.load_voice_profile_for)
            if _reconciled:
                print(f"[Dream] Voice gallery cache reconciled: {_reconciled} pid(s) out of sync")
            # Silent observations retention (prune_silent_observations() is implemented in db.py
            # but was never called — enforce SILENT_OBS_RETENTION_DAYS from config)
            db.prune_silent_observations()
            if config.DAILY_BACKUP_ENABLED:
                try:
                    from core.backup import run_daily_backup_pass
                    _loop = asyncio.get_event_loop()
                    _backup_result = await _loop.run_in_executor(
                        None,
                        lambda: run_daily_backup_pass(
                            [str(config.DB_PATH), str(config.BRAIN_DB_PATH)],
                            snapshot_dir=config.SNAPSHOT_DIR,
                            retention_days=config.SNAPSHOT_RETENTION_DAYS,
                        )
                    )
                    if _backup_result["snapshots_created"]:
                        print(f"[Backup] {len(_backup_result['snapshots_created'])} snapshot(s) created, "
                              f"{len(_backup_result['pruned'])} old pruned")
                    if _backup_result["errors"]:
                        print(f"[Backup] errors: {_backup_result['errors']}")
                except Exception as _e:
                    print(f"[Backup] pass failed: {_e!r}")
            # Wave 6 Item 22: hard-delete old invalidated knowledge.
            if config.KNOWLEDGE_HARD_DELETE_ENABLED:
                try:
                    await loop.run_in_executor(
                        None,
                        _wiring._brain_orchestrator.brain_db.hard_delete_old_invalidated_knowledge,
                    )
                except Exception as _e:
                    print(f"[Dream] hard-delete prune failed: {_e!r}")
            # Wave 6 Item 21: archive old conversation_log turns
            if config.CONVERSATION_ARCHIVE_ENABLED:
                try:
                    n_archived = await loop.run_in_executor(
                        None,
                        db.archive_old_conversation_log,
                    )
                    if n_archived:
                        print(f"[Dream] Conversation archive: {n_archived} turn(s) moved to archive DB")
                except Exception as _e:
                    print(f"[Dream] conversation archive failed: {_e!r}")
                # P0.R12 D1 — prune old rows from archive DB after archival;
                # bounds archive growth at CONVERSATION_ARCHIVE_RETENTION_DAYS
                # (~1 year default per Q1 (a) RATIFIED).
                try:
                    n_pruned = await loop.run_in_executor(
                        None,
                        db.prune_old_archive_conversation_log,
                    )
                    if n_pruned:
                        print(
                            f"[Dream] Archive-prune: {n_pruned} conversation_log row(s) "
                            f"deleted from archive (older than "
                            f"{config.CONVERSATION_ARCHIVE_RETENTION_DAYS}d)"
                        )
                except Exception as _e:
                    print(f"[Dream] archive prune failed: {_e!r}")  # CLEANUP: best-effort
            if config.WAL_CHECKPOINT_ENABLED:
                try:
                    db.checkpoint_wal()
                    _wiring._brain_orchestrator.brain_db.checkpoint_wal()
                    import core.classifier_graph as _cg_mod
                    _cg_mod.checkpoint_wal_singleton()
                    print("[Dream] WAL checkpoint complete (faces.db, brain.db, classifier.db)")
                except Exception as _wal_e:
                    print(f"[Dream] WAL checkpoint error: {_wal_e!r}")
            # P0.R11 D4 — prune persisted crash diagnostic JSON files older than
            # CRASH_LOG_RETENTION_DAYS. Matches archive_old_conversation_log
            # cadence (dream-loop trigger); per-file unlink failures swallowed
            # internally so a single corrupt file doesn't break the cleanup pass.
            try:
                from core.crash_logs import prune_old_crash_logs
                from core.config import CRASH_LOG_RETENTION_DAYS
                _crash_removed = await loop.run_in_executor(
                    None, prune_old_crash_logs, CRASH_LOG_RETENTION_DAYS
                )
                if _crash_removed > 0:
                    print(
                        f"[Dream] CrashLogs prune: {_crash_removed} file(s) "
                        f"older than {CRASH_LOG_RETENTION_DAYS}d removed"
                    )
            except Exception as _e:
                print(f"[Dream] crash-log prune failed: {_e!r}")
            # P0.R13 D2 — terminal_output.md size cap rotation + archive
            # retention pruning. Matches P0.R11 D4 crash-log prune cadence
            # (dream-loop trigger; amortized cleanup, not per-print hot path).
            try:
                _rotated = await loop.run_in_executor(
                    None, _check_terminal_output_size_cap
                )
                _archives_pruned = await loop.run_in_executor(
                    None, _prune_old_terminal_archives
                )
                if _archives_pruned > 0:
                    print(
                        f"[Dream] terminal_output archive prune: "
                        f"{_archives_pruned} file(s) older than "
                        f"{config.TERMINAL_OUTPUT_ARCHIVE_RETENTION_DAYS}d removed"
                    )
            except Exception as _e:
                print(f"[Dream] terminal output hygiene failed: {_e!r}")  # CLEANUP: best-effort
            _last_dream_at = time.time()
            _last_dream_run_at = time.time()
        # Smart sleep: wait out remaining cooldown to avoid 60× useless wakeups per hour.
        # Falls back to 60s when cooldown is expired but no idle window yet.
        remaining = max(0.0, _last_dream_at + DREAM_COOLDOWN - time.time())
        sleep_secs = remaining if remaining > 60.0 else 60.0
        try:
            await asyncio.wait_for(_wiring._shutdown_event.wait(), timeout=sleep_secs)
            return
        except asyncio.TimeoutError:
            pass
async def _emit_health(loop: asyncio.AbstractEventLoop) -> None:
    """Gather health + disk snapshots in executor and print summary lines."""
    from core.config import HEALTH_LOG_ENABLED, DISK_MONITOR_ENABLED
    from core.health import gather_health_snapshot, format_health_line, format_health_alerts
    from core.disk_monitor import gather_disk_snapshot, format_disk_line, check_disk_thresholds

    # Health snapshot
    if HEALTH_LOG_ENABLED:
        try:
            snapshot = await loop.run_in_executor(
                None,
                lambda: gather_health_snapshot(
                    db=_wiring._face_db_ref,
                    brain_orchestrator=_wiring._brain_orchestrator,
                    active_sessions=_wiring._session_store.peek_all_snapshots(),
                    cloud_state=_wiring._pipeline_state_store.peek_cloud_state(),
                    last_dream_run_at=_last_dream_run_at,
                ),
            )
            print(format_health_line(snapshot))
            for alert_line in format_health_alerts(snapshot, _wiring._brain_orchestrator):
                print(alert_line)
        except Exception as _e:
            print(f"[Health] emit failed: {_e!r}")

    # Disk snapshot
    if DISK_MONITOR_ENABLED:
        try:
            disk_snap = await loop.run_in_executor(None, gather_disk_snapshot)
            print(format_disk_line(disk_snap))
            check_disk_thresholds(disk_snap, _wiring._brain_orchestrator)
        except Exception as _e:
            print(f"[Disk] emit failed: {_e!r}")
async def _health_log_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Periodic health + disk log. First emission fires immediately at boot.

    P0.R2 D4: piggybacks `_vision_provider_state.maybe_retry_cuda(time.time())`
    call after each health snapshot to attempt CUDA restoration if the
    CPU-fallback timer (VISION_CUDA_RETRY_M_MINUTES) has elapsed.
    """
    from core.config import HEALTH_LOG_INTERVAL_SECS
    from core import vision_provider_state as _vps
    await _emit_health(loop)
    _vps.maybe_retry_cuda(time.time())
    while True:
        try:
            await asyncio.wait_for(_wiring._shutdown_event.wait(), timeout=HEALTH_LOG_INTERVAL_SECS)
            return
        except asyncio.TimeoutError:
            pass
        await _emit_health(loop)
        _vps.maybe_retry_cuda(time.time())
