"""P0.R11 crash diagnostic capture — 9 anchors per Plan v1 §3 LOCK.

Coverage map:
- A1: core/crash_logs.py module + 3 functions + _CRASH_LOG_SCHEMA_VERSION constant (source)
- A2: persist_crash_diagnostic writes JSON to FACES_DIR/crash_logs/ with correct filename shape (behavioral)
- A3: JSON payload includes all 7 fields (behavioral)
- A4: prune_old_crash_logs removes files older than retention_days (behavioral with backdated mtime)
- A5: list_recent_crash_logs returns most-recent N entries sorted by mtime desc (behavioral)
- A6: run_heavy invokes persist_crash_diagnostic on BrokenProcessPool — JSON file written + non-empty stack_trace (BEHAVIORAL per Observation 1 absorption; AST source-inspection alone would pass silently with missing import traceback)
- A7: HealthSnapshot.recent_crash_logs field + format_health_line crash_logs=N emit + format_health_alerts verbatim substrings
- A8: pipeline._dream_loop AST calls prune_old_crash_logs(CRASH_LOG_RETENTION_DAYS) (source)
- A9: 3 config constants present (source)
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import ast
import asyncio
import concurrent.futures
import concurrent.futures.process
import json
import os
import pathlib
import time

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


# ─────────────────────────────────────────────────────────────────────────────
# A1: core/crash_logs.py module + 3 functions + module-level constant
# ─────────────────────────────────────────────────────────────────────────────
def test_p0_r11_a1_crash_logs_module_present_with_3_functions_and_constant():
    src = (REPO_ROOT / "core" / "crash_logs.py").read_text(encoding="utf-8")
    assert "def persist_crash_diagnostic(" in src, "persist_crash_diagnostic function missing"
    assert "def prune_old_crash_logs(" in src, "prune_old_crash_logs function missing"
    assert "def list_recent_crash_logs(" in src, "list_recent_crash_logs function missing"
    assert "_CRASH_LOG_SCHEMA_VERSION = 1" in src, (
        "Module-level _CRASH_LOG_SCHEMA_VERSION = 1 constant missing"
    )

    # AST verification: all 3 functions exist as FunctionDef at module scope
    mod = ast.parse(src)
    fn_names = {n.name for n in mod.body if isinstance(n, ast.FunctionDef)}
    assert {"persist_crash_diagnostic", "prune_old_crash_logs", "list_recent_crash_logs"}.issubset(fn_names), (
        f"Expected 3 functions at module scope; found: {fn_names}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# A2: persist_crash_diagnostic writes JSON to FACES_DIR/crash_logs/ with sortable filename
# ─────────────────────────────────────────────────────────────────────────────
def test_p0_r11_a2_persist_writes_json_with_sortable_filename(tmp_path, monkeypatch):
    # Monkeypatch FACES_DIR to a temp dir
    monkeypatch.setattr("core.config.FACES_DIR", tmp_path)
    # Force re-import to pick up patched FACES_DIR
    from core import crash_logs
    exc = ValueError("test_exception_for_a2")
    now = 1717_000_000.123456  # known timestamp
    path = crash_logs.persist_crash_diagnostic(
        task_name="adaface_embed",
        exc=exc,
        traceback_str="Traceback...\n  fake\n",
        crash_count=1,
        now=now,
    )
    assert path is not None, "persist_crash_diagnostic returned None on happy path"
    assert path.exists(), f"JSON file not created at {path}"
    # Filename shape: adaface_embed_{YYYY-MM-DDTHHMMSS}_{micros}.json
    assert path.name.startswith("adaface_embed_"), f"Unexpected filename: {path.name}"
    assert path.name.endswith(".json"), f"Filename must end with .json: {path.name}"
    # Located under tmp_path/crash_logs/
    assert path.parent == tmp_path / "crash_logs", f"Expected parent crash_logs/, got {path.parent}"


# ─────────────────────────────────────────────────────────────────────────────
# A3: JSON payload includes all 7 fields
# ─────────────────────────────────────────────────────────────────────────────
def test_p0_r11_a3_json_payload_contains_all_7_fields(tmp_path, monkeypatch):
    monkeypatch.setattr("core.config.FACES_DIR", tmp_path)
    from core import crash_logs
    exc = RuntimeError("oh no")
    path = crash_logs.persist_crash_diagnostic(
        task_name="whisper_transcribe",
        exc=exc,
        traceback_str="Traceback...\n  some\n  stack\n",
        crash_count=2,
        now=1717_000_005.0,
    )
    assert path is not None
    data = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "schema_version",
        "task_name",
        "timestamp",
        "exception_type",
        "exception_message",
        "stack_trace",
        "crash_count",
    }
    actual = set(data.keys())
    assert required.issubset(actual), f"Missing fields: {required - actual}"
    assert data["schema_version"] == 1
    assert data["task_name"] == "whisper_transcribe"
    assert data["exception_type"] == "RuntimeError"
    assert data["exception_message"] == "oh no"
    assert "Traceback" in data["stack_trace"]
    assert data["crash_count"] == 2


# ─────────────────────────────────────────────────────────────────────────────
# A4: prune_old_crash_logs removes files older than retention_days
# ─────────────────────────────────────────────────────────────────────────────
def test_p0_r11_a4_prune_removes_old_files(tmp_path, monkeypatch):
    monkeypatch.setattr("core.config.FACES_DIR", tmp_path)
    from core import crash_logs
    # Create 3 files: 2 old, 1 fresh
    log_dir = tmp_path / "crash_logs"
    log_dir.mkdir()
    old1 = log_dir / "ecapa_embed_2026-04-01T000000_000000.json"
    old2 = log_dir / "ecapa_embed_2026-04-02T000000_000000.json"
    fresh = log_dir / "ecapa_embed_2026-05-25T000000_000000.json"
    for p in (old1, old2, fresh):
        p.write_text("{}", encoding="utf-8")
    # Backdate old files (10 days ago for retention_days=7)
    now = time.time()
    old_mtime = now - (10 * 86400)
    os.utime(old1, (old_mtime, old_mtime))
    os.utime(old2, (old_mtime, old_mtime))
    # fresh stays at current mtime
    removed = crash_logs.prune_old_crash_logs(retention_days=7, now=now)
    assert removed == 2, f"Expected 2 files removed, got {removed}"
    assert not old1.exists() and not old2.exists()
    assert fresh.exists(), "Fresh file incorrectly removed"


# ─────────────────────────────────────────────────────────────────────────────
# A5: list_recent_crash_logs returns most-recent N entries sorted by mtime desc
# ─────────────────────────────────────────────────────────────────────────────
def test_p0_r11_a5_list_recent_returns_sorted_by_mtime_desc(tmp_path, monkeypatch):
    monkeypatch.setattr("core.config.FACES_DIR", tmp_path)
    from core import crash_logs
    log_dir = tmp_path / "crash_logs"
    log_dir.mkdir()
    # Create 5 files with explicit timestamps
    base = time.time()
    files = []
    for i in range(5):
        p = log_dir / f"pyannote_diarize_2026-05-25T00000{i}_000000.json"
        p.write_text(json.dumps({"task_name": f"pyannote_diarize", "timestamp": base - i * 10, "id": i}), encoding="utf-8")
        # Backdate so file i has mtime = base - i*10 (file 0 most recent)
        os.utime(p, (base - i * 10, base - i * 10))
        files.append(p)
    # Limit 3 — expect entries with id 0, 1, 2 (most recent mtimes)
    results = crash_logs.list_recent_crash_logs(limit=3)
    assert len(results) == 3, f"Expected 3 entries, got {len(results)}"
    assert [r["id"] for r in results] == [0, 1, 2], (
        f"Expected sort order id=[0,1,2] descending mtime, got {[r['id'] for r in results]}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# A6: run_heavy invokes persist_crash_diagnostic on BrokenProcessPool —
# JSON file written + non-empty stack_trace (BEHAVIORAL; defense against missing-import)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_p0_r11_a6_run_heavy_writes_crash_log_on_broken_pool(tmp_path, monkeypatch):
    """Behavioral verification per Observation 1 absorption.

    Monkeypatch the pool to raise BrokenProcessPool on submit; invoke
    run_heavy; verify (i) a JSON file exists at FACES_DIR/crash_logs/ AND
    (ii) its stack_trace field is non-empty. This catches both missing-import
    silent-masking (revert i: remove `import traceback`) AND missing-as-e-binding
    silent-masking (revert without binding) shapes — AST source-inspection alone
    would pass even if either mutation was reverted because the outer
    `except Exception: pass` swallows NameError.
    """
    monkeypatch.setattr("core.config.FACES_DIR", tmp_path)

    import core.heavy_worker as hw

    # Monkeypatch pool to raise BrokenProcessPool when submit() is called.
    class _FakeBrokenPool:
        def submit(self, *args, **kwargs):
            raise concurrent.futures.process.BrokenProcessPool("synthetic crash")

        def shutdown(self, wait=True):
            pass

    # Inject fake pool into the registry so get_or_create_pool returns it.
    monkeypatch.setitem(hw._HEAVY_WORKER_POOLS, "p0_r11_a6_test", _FakeBrokenPool())

    # Snapshot crash_logs/ dir before
    log_dir = tmp_path / "crash_logs"
    pre_files = set(log_dir.glob("*.json")) if log_dir.exists() else set()

    def _no_op():
        return None

    with pytest.raises(concurrent.futures.process.BrokenProcessPool):
        await hw.run_heavy("p0_r11_a6_test", _no_op)

    # Verify a JSON file was written
    post_files = set(log_dir.glob("*.json")) if log_dir.exists() else set()
    new_files = post_files - pre_files
    assert len(new_files) >= 1, (
        f"A6 BEHAVIORAL: expected at least 1 new JSON crash log; got {len(new_files)}. "
        f"This catches missing `import traceback` silent-masking shape — if the import "
        f"is missing, NameError fires inside the try-block and outer `except Exception: pass` "
        f"swallows it, leaving no file written."
    )
    # Verify stack_trace field is non-empty
    new_file = next(iter(new_files))
    data = json.loads(new_file.read_text(encoding="utf-8"))
    assert "stack_trace" in data, f"stack_trace field missing in {data.keys()}"
    assert data["stack_trace"] and len(data["stack_trace"]) > 10, (
        f"A6 BEHAVIORAL: expected non-empty stack_trace; got: {data.get('stack_trace')!r}"
    )
    # Verify task_name matches
    assert data["task_name"] == "p0_r11_a6_test"
    # Verify exception_type
    assert data["exception_type"] == "BrokenProcessPool"


# ─────────────────────────────────────────────────────────────────────────────
# A7: HealthSnapshot.recent_crash_logs field + format_health_line crash_logs=N
#     + format_health_alerts verbatim substrings
# ─────────────────────────────────────────────────────────────────────────────
def test_p0_r11_a7_healthsnapshot_recent_crash_logs_field_and_format():
    from core import health
    from dataclasses import fields

    field_names = {f.name for f in fields(health.HealthSnapshot)}
    assert "recent_crash_logs" in field_names, (
        f"HealthSnapshot.recent_crash_logs field missing; got: {field_names}"
    )

    # Build a HealthSnapshot with non-empty recent_crash_logs and verify
    # format_health_line emits crash_logs=N
    now = time.time()
    snap = health.HealthSnapshot(
        timestamp=now,
        active_sessions=0,
        sessions_by_type={"best_friend": 0, "known": 0, "stranger": 0, "disputed": 0},
        persons_count=0,
        total_face_embeddings=0,
        knowledge_active_rows=0,
        shadow_persons_count=0,
        classifier_scenarios_active=0,
        classifier_scenarios_quarantined=0,
        cloud_state="OFFLINE",
        active_disputes=0,
        unresolved_watchdog_alerts=0,
        last_dream_run_seconds_ago=None,
        thin_voice_galleries=[],
        recent_crash_logs=[
            {"task_name": "adaface_embed", "timestamp": now - 100, "exception_type": "RuntimeError"},
            {"task_name": "whisper_transcribe", "timestamp": now - 200, "exception_type": "BrokenProcessPool"},
        ],
    )
    line = health.format_health_line(snap)
    assert "crash_logs=2" in line, f"Expected `crash_logs=2` in health line; got: {line}"

    # Verify format_health_alerts contains verbatim substrings
    class _StubBrain:
        class _stub:
            class _conn:
                @staticmethod
                def execute(*a, **kw):
                    return []
            _conn = _conn()
        _brain_db = _stub()
        _kuzu_degraded = False
    alerts = health.format_health_alerts(snap, _StubBrain())
    alerts_text = " ".join(alerts)
    assert "Recent crash logs available" in alerts_text, (
        f"Verbatim substring 'Recent crash logs available' missing: {alerts_text}"
    )
    assert "check faces/crash_logs/" in alerts_text, (
        f"Verbatim substring 'check faces/crash_logs/' missing: {alerts_text}"
    )
    assert "CRASH_LOG_RETENTION_DAYS" in alerts_text, (
        f"Verbatim substring 'CRASH_LOG_RETENTION_DAYS' missing: {alerts_text}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# A8: pipeline._dream_loop AST calls prune_old_crash_logs(CRASH_LOG_RETENTION_DAYS)
# ─────────────────────────────────────────────────────────────────────────────
def test_p0_r11_a8_dream_loop_calls_prune_old_crash_logs():
    src = (REPO_ROOT / "pipeline.py").read_text(encoding="utf-8")
    assert "prune_old_crash_logs" in src, "prune_old_crash_logs reference missing in pipeline.py"
    assert "CRASH_LOG_RETENTION_DAYS" in src, "CRASH_LOG_RETENTION_DAYS reference missing in pipeline.py"

    mod = ast.parse(src)
    found = False
    for node in ast.walk(mod):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_dream_loop":
            for sub in ast.walk(node):
                # Look for `loop.run_in_executor(None, prune_old_crash_logs, CRASH_LOG_RETENTION_DAYS)`
                # OR direct `prune_old_crash_logs(CRASH_LOG_RETENTION_DAYS)` call.
                if isinstance(sub, ast.Call):
                    src_str = ast.unparse(sub)
                    if (
                        "prune_old_crash_logs" in src_str
                        and "CRASH_LOG_RETENTION_DAYS" in src_str
                    ):
                        found = True
                        break
    assert found, (
        "A8: pipeline._dream_loop must call prune_old_crash_logs(CRASH_LOG_RETENTION_DAYS) "
        "(directly OR via loop.run_in_executor)"
    )


# ─────────────────────────────────────────────────────────────────────────────
# A9: 3 config constants present with sanity values
# ─────────────────────────────────────────────────────────────────────────────
def test_p0_r11_a9_config_constants_present():
    from core import config
    assert hasattr(config, "CRASH_LOG_RETENTION_DAYS"), "CRASH_LOG_RETENTION_DAYS missing"
    assert hasattr(config, "HEALTH_CRASH_LOG_RECENT_LIMIT"), "HEALTH_CRASH_LOG_RECENT_LIMIT missing"
    assert hasattr(config, "CRASH_LOG_SCHEMA_VERSION"), "CRASH_LOG_SCHEMA_VERSION missing"
    # Sanity values
    assert config.CRASH_LOG_RETENTION_DAYS == 7
    assert config.HEALTH_CRASH_LOG_RECENT_LIMIT == 10
    assert config.CRASH_LOG_SCHEMA_VERSION == 1
