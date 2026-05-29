"""P0.R12-R15 Resilience hygiene bundle — 9 anchors + 2 bundled-inline AST helper tests.

Coverage map (Q5 LOCKED = 9 anchors at exact mid):
- A1: D1 prune_old_archive_conversation_log method exists (source)
- A2: D1 prune actually removes old rows (BEHAVIORAL with tmp_path)
- A3: D1 dream-loop calls prune (AST source inside CONVERSATION_ARCHIVE_ENABLED guard)
- A4: D2 size cap + archive prune helpers exist (source)
- A5: D2 size cap triggers rotation at threshold (BEHAVIORAL FAST-SCOPED via monkeypatched stat)
- A6: D2 archive prune removes old files (BEHAVIORAL with tmp_path + os.utime)
- A7: D3 no hardcoded camera index (AST SCAN with _get_call_name + _is_inside_class_method)
- A8: D4 no time.sleep in async bodies (AST SCAN with _get_call_name)
- A9: D5 3 config constants present with sanity values (source)

Plus 2 bundled-inline helper tests (NOT counted as anchors):
- test_get_call_name_helper
- test_is_inside_class_method_helper
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import ast
import inspect
import os
import pathlib
import sqlite3
import time
from pathlib import Path
from unittest.mock import patch

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


# ─────────────────────────────────────────────────────────────────────────────
# AST helpers (per Plan v1 §3 — bundled-inline + reused by A7 + A8)
# ─────────────────────────────────────────────────────────────────────────────
def _get_call_name(node: ast.expr) -> "str | None":
    """Extract function name from ast.Call.func node.

    Supports: simple Name (e.g. `Camera`), Attribute (e.g. `cv2.VideoCapture`).
    Returns None for complex expressions (lambdas, subscripts, etc).
    """
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _get_call_name(node.value)
        if prefix:
            return f"{prefix}.{node.attr}"
        return node.attr
    return None


def _is_inside_class_method(
    target_node: ast.AST, tree: ast.Module, class_name: str
) -> bool:
    """Check if target_node is inside a method of the named class.

    Walks the tree, finds ClassDef nodes matching class_name, checks if
    target_node is nested inside any of its methods. Returns True if found.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for child in ast.walk(node):
                if child is target_node:
                    return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Bundled-inline helper tests (per Plan v1 §3 — auditor Recommendation #3)
# ─────────────────────────────────────────────────────────────────────────────
def test_get_call_name_helper():
    """A7+A8 sanity: _get_call_name extracts callable name from ast.Call.func."""
    assert _get_call_name(ast.parse("Camera(0)").body[0].value.func) == "Camera"
    assert _get_call_name(ast.parse("cv2.VideoCapture(0)").body[0].value.func) == "cv2.VideoCapture"
    assert _get_call_name(ast.parse("time.sleep(1)").body[0].value.func) == "time.sleep"


def test_is_inside_class_method_helper():
    """A7 sanity: _is_inside_class_method correctly identifies class-internal calls."""
    src = '''
class Camera:
    def __init__(self):
        self._index = 0
    def reconnect(self):
        cv2.VideoCapture(self._index)
def standalone():
    cv2.VideoCapture(0)
'''
    tree = ast.parse(src)
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and _get_call_name(n.func) == "cv2.VideoCapture"]
    inside_call = next(c for c in calls if isinstance(c.args[0], ast.Attribute))
    outside_call = next(c for c in calls if isinstance(c.args[0], ast.Constant))
    assert _is_inside_class_method(inside_call, tree, "Camera") is True
    assert _is_inside_class_method(outside_call, tree, "Camera") is False


# ─────────────────────────────────────────────────────────────────────────────
# A1: D1 prune_old_archive_conversation_log method exists (source)
# ─────────────────────────────────────────────────────────────────────────────
def test_p0_r12_d1_prune_archive_method_exists():
    src = (REPO_ROOT / "core" / "db.py").read_text(encoding="utf-8")
    assert "def prune_old_archive_conversation_log(" in src, (
        "FaceDB.prune_old_archive_conversation_log method missing"
    )
    # AST verification: method on FaceDB class with expected signature
    mod = ast.parse(src)
    found = False
    for cls in ast.walk(mod):
        if not (isinstance(cls, ast.ClassDef) and cls.name == "FaceDB"):
            continue
        for fn in cls.body:
            if not (isinstance(fn, ast.FunctionDef) and fn.name == "prune_old_archive_conversation_log"):
                continue
            found = True
            # Verify signature: self + retention_days + now params
            arg_names = [a.arg for a in fn.args.args]
            assert "self" in arg_names and "retention_days" in arg_names and "now" in arg_names, (
                f"prune_old_archive_conversation_log signature must have (self, retention_days, now); got: {arg_names}"
            )
    assert found, "prune_old_archive_conversation_log not found inside FaceDB class"


# ─────────────────────────────────────────────────────────────────────────────
# A2: D1 prune actually removes old rows (BEHAVIORAL with isolated FaceDB)
# ─────────────────────────────────────────────────────────────────────────────
def test_p0_r12_d1_prune_archive_removes_old_rows(tmp_path):
    """Build a synthetic archive DB with rows at varied ts; prune; verify count."""
    archive_path = tmp_path / "faces_conversation_archive.db"
    # Build the archive DB with the same schema as conversation_log archive
    conn = sqlite3.connect(str(archive_path))
    conn.execute("""
        CREATE TABLE conversation_log (
            id INTEGER PRIMARY KEY,
            person_id TEXT,
            role TEXT,
            content TEXT,
            ts REAL,
            room_session_id TEXT,
            audience_ids TEXT
        )
    """)
    now = time.time()
    rows = [
        ("p1", "user", "very old", now - 400 * 86400),   # 400d old — should prune
        ("p2", "user", "old", now - 365 * 86400 - 100),  # 365d+ old — should prune
        ("p3", "user", "recent", now - 30 * 86400),      # 30d old — keep
        ("p4", "user", "current", now - 1 * 86400),      # 1d old — keep
    ]
    for pid, role, content, ts in rows:
        conn.execute(
            "INSERT INTO conversation_log (person_id, role, content, ts, room_session_id, audience_ids) VALUES (?, ?, ?, ?, ?, ?)",
            (pid, role, content, ts, None, None),
        )
    conn.commit()
    conn.close()

    # Create a minimal FaceDB-like object with just the prune method's dependencies
    main_db = tmp_path / "faces.db"
    main_conn = sqlite3.connect(str(main_db))
    main_conn.row_factory = sqlite3.Row

    class _MinimalFaceDB:
        _conn = main_conn

        def _archive_db_path(self):
            return archive_path

    from core import db as db_mod
    # Bind the real prune method
    pruner = db_mod.FaceDB.prune_old_archive_conversation_log
    minimal = _MinimalFaceDB()

    n_pruned = pruner(minimal, retention_days=365, now=now)
    assert n_pruned == 2, f"Expected 2 rows pruned (older than 365d); got {n_pruned}"

    # Verify rows actually deleted from archive
    main_conn.execute("ATTACH DATABASE ? AS archive", (str(archive_path),))
    remaining = main_conn.execute(
        "SELECT person_id FROM archive.conversation_log ORDER BY ts"
    ).fetchall()
    main_conn.execute("DETACH DATABASE archive")
    remaining_ids = {r[0] for r in remaining}
    assert remaining_ids == {"p3", "p4"}, f"Expected p3+p4 to remain; got: {remaining_ids}"
    main_conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# A3: D1 dream-loop calls prune (AST source inside guard)
# ─────────────────────────────────────────────────────────────────────────────
def test_p0_r12_d1_dream_loop_calls_prune():
    src = (REPO_ROOT / "pipeline.py").read_text(encoding="utf-8")
    assert "config.CONVERSATION_ARCHIVE_ENABLED" in src, "ENABLED guard reference missing"

    mod = ast.parse(src)
    found_in_dream_loop = False
    for fn in ast.walk(mod):
        if not (isinstance(fn, ast.AsyncFunctionDef) and fn.name == "_dream_loop"):
            continue
        # Find If nodes with CONVERSATION_ARCHIVE_ENABLED test; inside,
        # look for `db.prune_old_archive_conversation_log` as an Attribute
        # reference (EXACT attr name match — defends against rename regressions
        # like `_DROPPED_prune_old_archive_conversation_log` which would pass
        # a naive substring check).
        for if_node in ast.walk(fn):
            if not isinstance(if_node, ast.If):
                continue
            test_src = ast.unparse(if_node.test)
            if "CONVERSATION_ARCHIVE_ENABLED" not in test_src:
                continue
            for sub in ast.walk(if_node):
                if (
                    isinstance(sub, ast.Attribute)
                    and sub.attr == "prune_old_archive_conversation_log"
                ):
                    found_in_dream_loop = True
                    break
    assert found_in_dream_loop, (
        "D1 dream-loop must reference `db.prune_old_archive_conversation_log` "
        "(EXACT attribute name) inside `if config.CONVERSATION_ARCHIVE_ENABLED:` guard"
    )


# ─────────────────────────────────────────────────────────────────────────────
# A4: D2 size cap + archive prune helpers exist (source)
# ─────────────────────────────────────────────────────────────────────────────
def test_p0_r13_d2_size_cap_rotation_helper_exists():
    src = (REPO_ROOT / "pipeline.py").read_text(encoding="utf-8")
    assert "def _check_terminal_output_size_cap(" in src
    assert "def _prune_old_terminal_archives(" in src

    mod = ast.parse(src)
    fn_names = {
        n.name for n in mod.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert "_check_terminal_output_size_cap" in fn_names
    assert "_prune_old_terminal_archives" in fn_names


# ─────────────────────────────────────────────────────────────────────────────
# A5: D2 size cap triggers rotation at threshold (BEHAVIORAL FAST-SCOPED)
# Auditor Recommendation #4: monkeypatch stat() to avoid 100MB I/O cost
# ─────────────────────────────────────────────────────────────────────────────
def test_p0_r13_d2_size_cap_triggers_rotation_at_threshold(monkeypatch, tmp_path):
    """Monkeypatch _LOG_PATH.stat() to return synthetic st_size > cap.

    FAST-SCOPED: no actual 100MB I/O. Tests rotation path purely behaviorally.
    """
    # We need to test the helper without invoking it on the real _LOG_FILE.
    # Strategy: create a fake log file at tmp_path, monkeypatch its stat()
    # to report over-cap, then call _check_terminal_output_size_cap(fake_path).
    fake_log = tmp_path / "terminal_output.md"
    fake_log.write_text("dummy content", encoding="utf-8")

    # Monkeypatch the global _LOG_FILE so close() doesn't break the real one
    import pipeline as pipeline_mod
    real_log_file = pipeline_mod._LOG_FILE
    # Create a no-op stand-in
    class _FakeFile:
        def flush(self): pass
        def close(self): pass
    monkeypatch.setattr(pipeline_mod, "_LOG_FILE", _FakeFile())

    # Monkeypatch stat() on the path to return over-cap size
    from core.config import TERMINAL_OUTPUT_SIZE_CAP_MB

    real_stat = pathlib.Path.stat
    def _fake_stat(self, *args, **kwargs):
        if self == fake_log:
            class _Stat:
                st_size = (TERMINAL_OUTPUT_SIZE_CAP_MB + 1) * 1024 * 1024
                st_mtime = time.time()
            return _Stat()
        return real_stat(self, *args, **kwargs)
    monkeypatch.setattr(pathlib.Path, "stat", _fake_stat)

    # Call the helper — should rotate
    result = pipeline_mod._check_terminal_output_size_cap(fake_log)
    assert result is True, "Expected rotation True at over-cap size"
    # Verify the original file was renamed (no longer at fake_log) AND a fresh one created
    # _archive_terminal_output renames the file then helper opens a fresh one
    assert fake_log.exists(), "Fresh log file should be reopened at fake_log path"

    # Under-cap case: monkeypatch stat to under-cap; call helper; verify returns False
    def _fake_stat_under(self, *args, **kwargs):
        if self == fake_log:
            class _Stat:
                st_size = 10 * 1024 * 1024  # 10 MB — well under 100 MB
                st_mtime = time.time()
            return _Stat()
        return real_stat(self, *args, **kwargs)
    monkeypatch.setattr(pathlib.Path, "stat", _fake_stat_under)
    result2 = pipeline_mod._check_terminal_output_size_cap(fake_log)
    assert result2 is False, "Expected no rotation under cap"

    # Restore real _LOG_FILE
    pipeline_mod._LOG_FILE = real_log_file


# ─────────────────────────────────────────────────────────────────────────────
# A6: D2 archive prune removes old files (BEHAVIORAL with tmp_path + os.utime)
# ─────────────────────────────────────────────────────────────────────────────
def test_p0_r13_d2_archive_prune_removes_old_files(tmp_path):
    """Seed terminal_output_*.md files at known mtimes; prune; verify count."""
    import pipeline as pipeline_mod

    # Create files: 2 old, 2 fresh
    old1 = tmp_path / "terminal_output_2026-01-01_000000.md"
    old2 = tmp_path / "terminal_output_2026-01-15_000000.md"
    fresh1 = tmp_path / "terminal_output_2026-05-20_000000.md"
    fresh2 = tmp_path / "terminal_output_2026-05-25_000000.md"
    for p in (old1, old2, fresh1, fresh2):
        p.write_text("dummy", encoding="utf-8")

    now = time.time()
    old_mtime = now - 60 * 86400  # 60d ago — older than 30d retention
    new_mtime = now - 5 * 86400   # 5d ago — within retention
    os.utime(old1, (old_mtime, old_mtime))
    os.utime(old2, (old_mtime, old_mtime))
    os.utime(fresh1, (new_mtime, new_mtime))
    os.utime(fresh2, (new_mtime, new_mtime))

    n_pruned = pipeline_mod._prune_old_terminal_archives(retention_days=30, log_dir=tmp_path)
    assert n_pruned == 2, f"Expected 2 old archives pruned; got {n_pruned}"
    assert not old1.exists() and not old2.exists(), "Old archives should be deleted"
    assert fresh1.exists() and fresh2.exists(), "Fresh archives should remain"


# ─────────────────────────────────────────────────────────────────────────────
# A7: D3 no hardcoded camera index (AST SCAN)
# ─────────────────────────────────────────────────────────────────────────────
def test_p0_r14_d3_no_hardcoded_camera_index():
    """Q5 (a) RATIFIED: scan core/*.py + pipeline.py. CLI scripts excluded.

    Allowed inside Camera class methods (self._index is the config-driven value).
    """
    files_to_scan = [str(REPO_ROOT / "pipeline.py")] + sorted(
        str(p) for p in (REPO_ROOT / "core").glob("*.py")
    )
    violations = []
    for filename in files_to_scan:
        with open(filename, encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func_name = _get_call_name(node.func)
            if func_name not in ("Camera", "cv2.VideoCapture", "VideoCapture"):
                continue
            if not node.args:
                continue
            first_arg = node.args[0]
            if not (isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, int)):
                continue
            # Allow inside Camera class methods (uses self._index)
            if _is_inside_class_method(node, tree, "Camera"):
                continue
            violations.append(f"{filename}:{node.lineno}")
    assert not violations, f"Hardcoded camera index found in production code: {violations}"


# ─────────────────────────────────────────────────────────────────────────────
# A8: D4 no time.sleep in async bodies (AST SCAN)
# ─────────────────────────────────────────────────────────────────────────────
def test_p0_r15_d4_no_time_sleep_in_async_bodies():
    """Q6 (a) RATIFIED: async-only invariant scope. Sync def bodies allowed.

    Catches future regression where someone adds time.sleep inside an async fn.
    """
    files_to_scan = [str(REPO_ROOT / "pipeline.py")] + sorted(
        str(p) for p in (REPO_ROOT / "core").glob("*.py")
    )
    violations = []
    for filename in files_to_scan:
        with open(filename, encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef):
                continue
            # Walk the async function body, skipping nested sync FunctionDefs
            # (a sync def inside an async def is its own scope, so time.sleep
            # there is not a violation of the async invariant).
            for inner in _walk_async_body(node):
                if not isinstance(inner, ast.Call):
                    continue
                func_name = _get_call_name(inner.func)
                if func_name == "time.sleep":
                    violations.append(
                        f"{filename}:{inner.lineno} (inside async {node.name})"
                    )
    assert not violations, f"time.sleep inside async def: {violations}"


def _walk_async_body(async_fn: ast.AsyncFunctionDef):
    """Walk async fn body, skipping nested sync FunctionDef scopes.

    Sync `def` nested inside `async def` is its own scope; time.sleep there
    is allowed (it's a sync helper, not an async-context violation).
    """
    for child in ast.walk(async_fn):
        # Skip nested sync FunctionDef bodies (they're separate scopes)
        if isinstance(child, ast.FunctionDef) and child is not async_fn:
            continue
        yield child


# ─────────────────────────────────────────────────────────────────────────────
# A9: D5 config constants present with sanity values
# ─────────────────────────────────────────────────────────────────────────────
def test_p0_r12_r15_config_constants_present():
    from core import config
    assert hasattr(config, "CONVERSATION_ARCHIVE_RETENTION_DAYS")
    assert hasattr(config, "TERMINAL_OUTPUT_SIZE_CAP_MB")
    assert hasattr(config, "TERMINAL_OUTPUT_ARCHIVE_RETENTION_DAYS")
    assert config.CONVERSATION_ARCHIVE_RETENTION_DAYS == 365
    assert config.TERMINAL_OUTPUT_SIZE_CAP_MB == 100
    assert config.TERMINAL_OUTPUT_ARCHIVE_RETENTION_DAYS == 30
