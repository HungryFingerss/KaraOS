"""Coverage-to-100 campaign — runtime/background_loops.py (the background-task engine surface).

Exercises every line of the run()-spawned background loops (_dream_loop, _health_log_loop),
the conversation_turn-spawned _cloud_retry_loop, and the _emit_health monitoring helper.
Every external boundary — the DB, the brain orchestrator, the backup / crash-log / WAL /
health / disk helpers, the shutdown Event, the `time` module, and asyncio.wait_for — is
mocked so the suite runs headless (no GPU, camera, network, or model downloads). asyncio_mode
is `auto`, so the `async def test_*` bodies need no marker.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

import asyncio
import time as _time
from unittest.mock import AsyncMock, MagicMock, patch

import core.config as _config
import runtime.background_loops as bl
import runtime.wiring as _wiring
from runtime.state_enums import CloudState


# ─────────────────────────────────────────────────────────────────────────────
# _cloud_retry_loop
# ─────────────────────────────────────────────────────────────────────────────
def _cloud_store(state, failed_at=0.0):
    store = MagicMock()
    store.peek_cloud_state = MagicMock(return_value=state)
    store.peek_cloud_failed_at = MagicMock(return_value=failed_at)
    store.transition_to_online = AsyncMock()
    return store


async def test_cloud_retry_loop_returns_on_shutdown_during_wait():
    """Line 42 — a shutdown set while awaiting the retry interval exits the loop cleanly."""
    event = asyncio.Event()
    store = _cloud_store(CloudState.SICK)
    ping = AsyncMock(return_value=True)
    with patch.object(bl, "CLOUD_RETRY_INTERVAL", 100), \
         patch.object(bl, "ping_together", ping), \
         patch.object(_wiring, "_shutdown_event", event), \
         patch.object(_wiring, "_pipeline_state_store", store), \
         patch.object(_wiring, "_brain_orchestrator", MagicMock()):
        task = asyncio.create_task(bl._cloud_retry_loop())
        await asyncio.sleep(0.02)   # let the loop reach `wait_for(event.wait(), 100)`
        event.set()                 # shutdown requested mid-wait
        await asyncio.wait_for(task, timeout=1.0)
    ping.assert_not_awaited()       # returned before the ONLINE check / ping


async def test_cloud_retry_loop_skips_ping_when_online():
    """Lines 43-47 — while ONLINE the loop skips ping_together and keeps looping."""
    event = asyncio.Event()
    store = _cloud_store(CloudState.ONLINE)
    ping_calls = []

    async def fake_ping():
        ping_calls.append(1)
        return True

    with patch.object(bl, "CLOUD_RETRY_INTERVAL", 0.02), \
         patch.object(bl, "ping_together", fake_ping), \
         patch.object(_wiring, "_shutdown_event", event), \
         patch.object(_wiring, "_pipeline_state_store", store), \
         patch.object(_wiring, "_brain_orchestrator", MagicMock()):
        task = asyncio.create_task(bl._cloud_retry_loop())
        await asyncio.sleep(0.07)   # >= 2 interval timeouts → ONLINE `continue` twice
        event.set()
        await asyncio.wait_for(task, timeout=1.0)
    assert ping_calls == []                       # ping never called while ONLINE
    assert store.peek_cloud_state.call_count >= 1  # the ONLINE check ran each loop


async def test_cloud_retry_loop_recovery_with_orchestrator(capsys):
    """Lines 49-55 — a successful ping transitions ONLINE and reports API recovery."""
    event = asyncio.Event()
    store = _cloud_store(CloudState.SICK, failed_at=_time.monotonic() - 5)
    orch = MagicMock()

    async def fake_ping():
        event.set()   # single iteration then exit
        return True

    with patch.object(bl, "CLOUD_RETRY_INTERVAL", 0.01), \
         patch.object(bl, "ping_together", fake_ping), \
         patch.object(_wiring, "_shutdown_event", event), \
         patch.object(_wiring, "_pipeline_state_store", store), \
         patch.object(_wiring, "_brain_orchestrator", orch):
        await asyncio.wait_for(bl._cloud_retry_loop(), timeout=1.0)
        await asyncio.sleep(0.02)   # flush the create_task(transition_to_online())
    store.transition_to_online.assert_awaited_once()
    orch.report_api_recovered.assert_called_once()
    assert "reconnected" in capsys.readouterr().out


async def test_cloud_retry_loop_recovery_without_orchestrator():
    """Line 54 (False) — recovery still transitions ONLINE when no orchestrator exists."""
    event = asyncio.Event()
    store = _cloud_store(CloudState.SICK)

    async def fake_ping():
        event.set()
        return True

    with patch.object(bl, "CLOUD_RETRY_INTERVAL", 0.01), \
         patch.object(bl, "ping_together", fake_ping), \
         patch.object(_wiring, "_shutdown_event", event), \
         patch.object(_wiring, "_pipeline_state_store", store), \
         patch.object(_wiring, "_brain_orchestrator", None):
        await asyncio.wait_for(bl._cloud_retry_loop(), timeout=1.0)
        await asyncio.sleep(0.02)
    store.transition_to_online.assert_awaited_once()   # line 53 fires regardless


async def test_cloud_retry_loop_failure_reports_with_orchestrator(capsys):
    """Lines 56-59 — a failed ping while cloud_failed_at is set reports the outage duration."""
    event = asyncio.Event()
    store = _cloud_store(CloudState.SICK, failed_at=_time.monotonic() - 5)
    orch = MagicMock()

    async def fake_ping():
        event.set()
        return False

    with patch.object(bl, "CLOUD_RETRY_INTERVAL", 0.01), \
         patch.object(bl, "ping_together", fake_ping), \
         patch.object(_wiring, "_shutdown_event", event), \
         patch.object(_wiring, "_pipeline_state_store", store), \
         patch.object(_wiring, "_brain_orchestrator", orch):
        await asyncio.wait_for(bl._cloud_retry_loop(), timeout=1.0)
    orch.report_api_failure.assert_called_once()
    store.transition_to_online.assert_not_awaited()
    assert "Retrying" in capsys.readouterr().out


async def test_cloud_retry_loop_failure_without_orchestrator():
    """Line 56 (False) — the elif short-circuits when no orchestrator is available."""
    event = asyncio.Event()
    store = _cloud_store(CloudState.SICK, failed_at=_time.monotonic() - 5)

    async def fake_ping():
        event.set()
        return False

    with patch.object(bl, "CLOUD_RETRY_INTERVAL", 0.01), \
         patch.object(bl, "ping_together", fake_ping), \
         patch.object(_wiring, "_shutdown_event", event), \
         patch.object(_wiring, "_pipeline_state_store", store), \
         patch.object(_wiring, "_brain_orchestrator", None):
        await asyncio.wait_for(bl._cloud_retry_loop(), timeout=1.0)
    # `peek_cloud_failed_at()` is the left operand of the elif → still evaluated.
    store.peek_cloud_failed_at.assert_called()


# ─────────────────────────────────────────────────────────────────────────────
# _dream_loop
# ─────────────────────────────────────────────────────────────────────────────
def _dream_db(pruned=None, stale=None, sizes=None, n_archived=1, n_pruned=1):
    stale = stale if stale is not None else []
    db = MagicMock()
    db.prune_old_strangers_async = AsyncMock(return_value=pruned if pruned is not None else [])
    db.find_stale_stranger_voice_ids = MagicMock(return_value=stale)
    db.prune_stale_stranger_voice = MagicMock(return_value=stale)
    db.load_voice_profile_sizes = MagicMock(return_value=sizes if sizes is not None else {})
    db.load_voice_profile_for = MagicMock(return_value=object())
    db.prune_silent_observations = MagicMock()
    db.archive_old_conversation_log = MagicMock(return_value=n_archived)
    db.prune_old_archive_conversation_log = MagicMock(return_value=n_pruned)
    db.checkpoint_wal = MagicMock()
    return db


def _dream_vgs(reconciled=0):
    vgs = MagicMock()
    vgs.pop_gallery = AsyncMock()
    vgs.reconcile = AsyncMock(return_value=reconciled)
    return vgs


async def test_dream_loop_returns_on_shutdown_during_initial_wait():
    """Line 72 — a shutdown set before the settle-delay elapses exits before the body."""
    event = asyncio.Event()
    event.set()   # already shutting down
    db = _dream_db()
    with patch.object(_wiring, "_shutdown_event", event), \
         patch.object(bl, "DREAM_IDLE_MINUTES", 100):
        await asyncio.wait_for(bl._dream_loop(db), timeout=1.0)
    db.prune_old_strangers_async.assert_not_awaited()   # never entered the body


async def test_dream_loop_full_body_all_flags_enabled(capsys):
    """The complete idle-consolidation body with every flag on and every optional
    print branch truthy (lines 82-223 happy path)."""
    event = asyncio.Event()
    orch = MagicMock()
    orch.dream = AsyncMock()
    db = _dream_db(pruned=["s1"], stale=["st1"], sizes={"p": 5}, n_archived=5, n_pruned=2)
    vgs = _dream_vgs(reconciled=1)
    fake_time = MagicMock()
    fake_time.time.return_value = 1.0
    backup_result = {"snapshots_created": ["snap1"], "pruned": ["old1"], "errors": ["e1"]}

    with patch.object(_wiring, "_shutdown_event", event), \
         patch.object(_wiring, "_brain_orchestrator", orch), \
         patch.object(bl, "_voice_gallery_store", vgs), \
         patch.object(bl, "time", fake_time), \
         patch.object(bl, "DREAM_IDLE_MINUTES", 0), \
         patch.object(bl, "DREAM_COOLDOWN", 0), \
         patch.object(bl, "DREAM_MAX_INTERVAL", 99999), \
         patch.object(_config, "DAILY_BACKUP_ENABLED", True), \
         patch.object(_config, "KNOWLEDGE_HARD_DELETE_ENABLED", True), \
         patch.object(_config, "CONVERSATION_ARCHIVE_ENABLED", True), \
         patch.object(_config, "WAL_CHECKPOINT_ENABLED", True), \
         patch("core.backup.run_daily_backup_pass", MagicMock(return_value=backup_result)), \
         patch("core.crash_logs.prune_old_crash_logs", MagicMock(return_value=3)), \
         patch("core.classifier_graph.checkpoint_wal_singleton", MagicMock()), \
         patch.object(bl, "_check_terminal_output_size_cap", MagicMock(return_value=True)), \
         patch.object(bl, "_prune_old_terminal_archives", MagicMock(return_value=4)):

        async def _stop():
            await asyncio.sleep(0.3)
            event.set()

        await asyncio.gather(bl._dream_loop(db), _stop())

    orch.dream.assert_awaited()
    out = capsys.readouterr().out
    assert "Starting consolidation cycle" in out
    assert "Strangers pruned: 1" in out
    assert "Stale stranger voice rows pruned: 1" in out
    assert "Voice gallery cache reconciled: 1" in out
    assert "[Backup] 1 snapshot(s) created" in out
    assert "[Backup] errors:" in out
    assert "Conversation archive: 5" in out
    assert "Archive-prune: 2" in out
    assert "WAL checkpoint complete" in out
    assert "CrashLogs prune: 3" in out
    assert "terminal_output archive prune: 4" in out


async def test_dream_loop_force_trigger_with_flags_disabled(capsys):
    """Line 84 (force trigger during active session) + the flag-disabled skips
    (lines 123/143/152/178 False) + the empty-result branches (93/102/118 False)."""
    event = asyncio.Event()
    orch = MagicMock()
    orch.dream = AsyncMock()
    db = _dream_db()                      # all empty returns
    vgs = _dream_vgs(reconciled=0)
    fake_time = MagicMock()
    fake_time.time.return_value = 1.0
    await _wiring._session_store.open_session("p1", "unknown", "stranger", "face", now=0.0)

    with patch.object(_wiring, "_shutdown_event", event), \
         patch.object(_wiring, "_brain_orchestrator", orch), \
         patch.object(bl, "_voice_gallery_store", vgs), \
         patch.object(bl, "time", fake_time), \
         patch.object(bl, "DREAM_IDLE_MINUTES", 0), \
         patch.object(bl, "DREAM_COOLDOWN", 99999), \
         patch.object(bl, "DREAM_MAX_INTERVAL", 0), \
         patch.object(_config, "DAILY_BACKUP_ENABLED", False), \
         patch.object(_config, "KNOWLEDGE_HARD_DELETE_ENABLED", False), \
         patch.object(_config, "CONVERSATION_ARCHIVE_ENABLED", False), \
         patch.object(_config, "WAL_CHECKPOINT_ENABLED", False), \
         patch("core.crash_logs.prune_old_crash_logs", MagicMock(return_value=0)), \
         patch.object(bl, "_check_terminal_output_size_cap", MagicMock(return_value=False)), \
         patch.object(bl, "_prune_old_terminal_archives", MagicMock(return_value=0)):

        async def _stop():
            await asyncio.sleep(0.3)
            event.set()

        await asyncio.gather(bl._dream_loop(db), _stop())

    out = capsys.readouterr().out
    assert "Force trigger" in out
    orch.dream.assert_awaited()


async def test_dream_loop_skips_body_when_busy_and_not_forced():
    """Line 82 (False) — an active session with cooldown unmet skips the body entirely,
    and the `remaining > 60` smart-sleep branch (line 227) is taken."""
    event = asyncio.Event()
    orch = MagicMock()
    orch.dream = AsyncMock()
    db = _dream_db()
    fake_time = MagicMock()
    fake_time.time.return_value = 1.0
    await _wiring._session_store.open_session("p1", "unknown", "stranger", "face", now=0.0)

    with patch.object(_wiring, "_shutdown_event", event), \
         patch.object(_wiring, "_brain_orchestrator", orch), \
         patch.object(bl, "time", fake_time), \
         patch.object(bl, "DREAM_IDLE_MINUTES", 0), \
         patch.object(bl, "DREAM_COOLDOWN", 99999), \
         patch.object(bl, "DREAM_MAX_INTERVAL", 99999):

        async def _stop():
            await asyncio.sleep(0.2)
            event.set()

        await asyncio.gather(bl._dream_loop(db), _stop())

    orch.dream.assert_not_awaited()   # body skipped


async def test_dream_loop_exception_paths(capsys):
    """Every guarded try/except in the body (lines 140-141, 149-150, 160-161,
    176-177, 185-186, 202-203, 220-221) — each maintenance call raises and is caught."""
    event = asyncio.Event()
    orch = MagicMock()
    orch.dream = AsyncMock()
    orch.brain_db.hard_delete_old_invalidated_knowledge = MagicMock(side_effect=RuntimeError("hd"))
    db = _dream_db()
    db.archive_old_conversation_log = MagicMock(side_effect=RuntimeError("arch"))
    db.prune_old_archive_conversation_log = MagicMock(side_effect=RuntimeError("aprune"))
    db.checkpoint_wal = MagicMock(side_effect=RuntimeError("wal"))
    vgs = _dream_vgs(reconciled=0)
    fake_time = MagicMock()
    fake_time.time.return_value = 1.0

    with patch.object(_wiring, "_shutdown_event", event), \
         patch.object(_wiring, "_brain_orchestrator", orch), \
         patch.object(bl, "_voice_gallery_store", vgs), \
         patch.object(bl, "time", fake_time), \
         patch.object(bl, "DREAM_IDLE_MINUTES", 0), \
         patch.object(bl, "DREAM_COOLDOWN", 0), \
         patch.object(bl, "DREAM_MAX_INTERVAL", 99999), \
         patch.object(_config, "DAILY_BACKUP_ENABLED", True), \
         patch.object(_config, "KNOWLEDGE_HARD_DELETE_ENABLED", True), \
         patch.object(_config, "CONVERSATION_ARCHIVE_ENABLED", True), \
         patch.object(_config, "WAL_CHECKPOINT_ENABLED", True), \
         patch("core.backup.run_daily_backup_pass", MagicMock(side_effect=RuntimeError("bk"))), \
         patch("core.crash_logs.prune_old_crash_logs", MagicMock(side_effect=RuntimeError("cl"))), \
         patch.object(bl, "_check_terminal_output_size_cap", MagicMock(side_effect=RuntimeError("tc"))), \
         patch.object(bl, "_prune_old_terminal_archives", MagicMock(return_value=0)):

        async def _stop():
            await asyncio.sleep(0.3)
            event.set()

        await asyncio.gather(bl._dream_loop(db), _stop())

    out = capsys.readouterr().out
    assert "[Backup] pass failed" in out
    assert "hard-delete prune failed" in out
    assert "conversation archive failed" in out
    assert "archive prune failed" in out
    assert "WAL checkpoint error" in out
    assert "crash-log prune failed" in out
    assert "terminal output hygiene failed" in out


async def test_dream_loop_smart_sleep_timeout_then_shutdown():
    """Lines 231-232 — a smart-sleep timeout loops the body a second time (which also
    covers the `_last_dream_at > 0` idle-minutes branch on line 85), then a shutdown returns."""
    event = asyncio.Event()
    orch = MagicMock()
    orch.dream = AsyncMock()
    db = _dream_db()
    vgs = _dream_vgs(reconciled=0)
    fake_time = MagicMock()
    fake_time.time.return_value = 1.0

    _real_wait_for = asyncio.wait_for
    calls = {"n": 0}

    async def _fake_wait_for(awaitable, timeout):
        calls["n"] += 1
        if calls["n"] <= 2:                 # 1: initial wait, 2: first smart-sleep
            awaitable.close()               # skip the event.wait() coroutine cleanly
            raise asyncio.TimeoutError
        event.set()                         # 3: second smart-sleep → shut the loop down
        return await _real_wait_for(awaitable, timeout)

    with patch.object(_wiring, "_shutdown_event", event), \
         patch.object(_wiring, "_brain_orchestrator", orch), \
         patch.object(bl, "_voice_gallery_store", vgs), \
         patch.object(bl, "time", fake_time), \
         patch.object(bl, "DREAM_IDLE_MINUTES", 0), \
         patch.object(bl, "DREAM_COOLDOWN", 0), \
         patch.object(bl, "DREAM_MAX_INTERVAL", 99999), \
         patch.object(_config, "DAILY_BACKUP_ENABLED", False), \
         patch.object(_config, "KNOWLEDGE_HARD_DELETE_ENABLED", False), \
         patch.object(_config, "CONVERSATION_ARCHIVE_ENABLED", False), \
         patch.object(_config, "WAL_CHECKPOINT_ENABLED", False), \
         patch("core.crash_logs.prune_old_crash_logs", MagicMock(return_value=0)), \
         patch.object(bl, "_check_terminal_output_size_cap", MagicMock(return_value=False)), \
         patch.object(bl, "_prune_old_terminal_archives", MagicMock(return_value=0)), \
         patch.object(asyncio, "wait_for", _fake_wait_for):
        await bl._dream_loop(db)

    assert calls["n"] == 3            # initial wait + 2 smart-sleep waits
    assert orch.dream.await_count == 2   # the body consolidated twice


# ─────────────────────────────────────────────────────────────────────────────
# _emit_health
# ─────────────────────────────────────────────────────────────────────────────
async def test_emit_health_both_enabled_success(capsys):
    """Lines 240-263 — both blocks enabled: line printed, every alert emitted, disk checked."""
    loop = asyncio.get_running_loop()
    with patch.object(_config, "HEALTH_LOG_ENABLED", True), \
         patch.object(_config, "DISK_MONITOR_ENABLED", True), \
         patch("core.health.gather_health_snapshot", MagicMock(return_value=MagicMock())), \
         patch("core.health.format_health_line", MagicMock(return_value="[Health] line")), \
         patch("core.health.format_health_alerts", MagicMock(return_value=["alert-A", "alert-B"])), \
         patch("core.disk_monitor.gather_disk_snapshot", MagicMock(return_value=MagicMock())), \
         patch("core.disk_monitor.format_disk_line", MagicMock(return_value="[Disk] line")), \
         patch("core.disk_monitor.check_disk_thresholds", MagicMock()) as chk:
        await bl._emit_health(loop)
    out = capsys.readouterr().out
    assert "[Health] line" in out
    assert "alert-A" in out and "alert-B" in out   # the format_health_alerts loop iterated
    assert "[Disk] line" in out
    chk.assert_called_once()


async def test_emit_health_exception_paths(capsys):
    """Lines 255-256 and 264-265 — both gather calls raise and are caught + logged."""
    loop = asyncio.get_running_loop()
    with patch.object(_config, "HEALTH_LOG_ENABLED", True), \
         patch.object(_config, "DISK_MONITOR_ENABLED", True), \
         patch("core.health.gather_health_snapshot", MagicMock(side_effect=RuntimeError("h"))), \
         patch("core.health.format_health_line", MagicMock()), \
         patch("core.health.format_health_alerts", MagicMock(return_value=[])), \
         patch("core.disk_monitor.gather_disk_snapshot", MagicMock(side_effect=RuntimeError("d"))), \
         patch("core.disk_monitor.format_disk_line", MagicMock()), \
         patch("core.disk_monitor.check_disk_thresholds", MagicMock()):
        await bl._emit_health(loop)
    out = capsys.readouterr().out
    assert "[Health] emit failed" in out
    assert "[Disk] emit failed" in out


async def test_emit_health_both_disabled(capsys):
    """Lines 240 / 259 (False) — both flags off skips the health and disk blocks."""
    loop = asyncio.get_running_loop()
    with patch.object(_config, "HEALTH_LOG_ENABLED", False), \
         patch.object(_config, "DISK_MONITOR_ENABLED", False):
        await bl._emit_health(loop)
    out = capsys.readouterr().out
    assert "[Health]" not in out
    assert "[Disk]" not in out


# ─────────────────────────────────────────────────────────────────────────────
# _health_log_loop
# ─────────────────────────────────────────────────────────────────────────────
async def test_health_log_loop_emits_then_loops_then_returns():
    """Lines 273-284 — boot emit + CUDA retry, one timeout iteration (post-timeout emit),
    then a shutdown return."""
    loop = asyncio.get_running_loop()
    event = asyncio.Event()
    emit = AsyncMock()

    _real_wait_for = asyncio.wait_for
    calls = {"n": 0}

    async def _fake_wait_for(awaitable, timeout):
        calls["n"] += 1
        if calls["n"] == 1:               # first while-iteration times out
            awaitable.close()
            raise asyncio.TimeoutError
        event.set()                       # second while-iteration shuts down
        return await _real_wait_for(awaitable, timeout)

    with patch.object(_wiring, "_shutdown_event", event), \
         patch.object(bl, "_emit_health", emit), \
         patch("core.vision_provider_state.maybe_retry_cuda", MagicMock()) as retry, \
         patch.object(asyncio, "wait_for", _fake_wait_for):
        await bl._health_log_loop(loop)

    assert emit.await_count == 2      # boot emit (275) + post-timeout emit (283)
    assert retry.call_count == 2      # maybe_retry_cuda after each emit (276 + 284)
    assert calls["n"] == 2            # one timeout, one shutdown-return
