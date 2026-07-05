"""100% line coverage for core.dashboard_token — coverage-to-100 campaign.

Exercises the defensive/error branches the P0.S2 happy-path tests skip:
fsync/chmod OSError swallows, icacls FileNotFoundError + TimeoutExpired,
partial-write cleanup races, POSIX mode self-heal drift/chmod-fail, an
unreadable existing token, and the corrupt-token copy-then-unlink fallback.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import getpass
import os
import subprocess
import types
from pathlib import Path

import core.dashboard_token as dt


# ───────────────────────────────────────────────────────────────────────
# _atomic_write_secret — best-effort fsync + chmod swallows (lines 57-58, 61-62)
# ───────────────────────────────────────────────────────────────────────


def test_atomic_write_secret_survives_fsync_oserror(tmp_path, monkeypatch):
    """Lines 57-58: os.fsync raising OSError is swallowed; file still written."""
    def _boom_fsync(_fd):
        raise OSError("fsync unsupported on this filesystem")

    monkeypatch.setattr(os, "fsync", _boom_fsync)
    path = tmp_path / ".dashboard_token"
    dt._atomic_write_secret(path, "hello-content")
    assert path.read_bytes().decode() == "hello-content"


def test_atomic_write_secret_survives_chmod_oserror(tmp_path, monkeypatch):
    """Lines 61-62: os.chmod raising OSError on the tmp file is swallowed;
    the atomic os.replace still lands the canonical file."""
    real_chmod = os.chmod

    def _fake_chmod(p, mode, *a, **k):
        if ".tmp." in str(p):
            raise OSError("chmod denied on tmp artifact")
        return real_chmod(p, mode, *a, **k)

    monkeypatch.setattr(os, "chmod", _fake_chmod)
    path = tmp_path / ".dashboard_token"
    dt._atomic_write_secret(path, "chmod-fail-content")
    assert path.read_bytes().decode() == "chmod-fail-content"


# ───────────────────────────────────────────────────────────────────────
# _apply_windows_acl — success, nonzero rc, missing binary, timeout
# (lines 82-90 success/warn + 91-104 error branches)
# ───────────────────────────────────────────────────────────────────────


def test_apply_windows_acl_returns_true_on_success(monkeypatch):
    """Lines 82-83: icacls returncode 0 -> True."""
    monkeypatch.setattr(getpass, "getuser", lambda: "testuser")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda cmd, **k: types.SimpleNamespace(returncode=0, stdout="", stderr=""),
    )
    assert dt._apply_windows_acl("C:/fake/token") is True


def test_apply_windows_acl_returns_false_on_nonzero_rc(monkeypatch, capsys):
    """Lines 84-90: icacls returncode != 0 -> WARNING + False."""
    monkeypatch.setattr(getpass, "getuser", lambda: "testuser")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda cmd, **k: types.SimpleNamespace(returncode=5, stdout="out", stderr="err"),
    )
    assert dt._apply_windows_acl("C:/fake/token") is False
    assert "icacls failed" in capsys.readouterr().out


def test_apply_windows_acl_handles_icacls_missing(monkeypatch, capsys):
    """Lines 91-98: icacls not on PATH -> FileNotFoundError -> WARNING + False."""
    monkeypatch.setattr(getpass, "getuser", lambda: "testuser")

    def _boom_run(cmd, **k):
        raise FileNotFoundError("icacls not found")

    monkeypatch.setattr(subprocess, "run", _boom_run)
    assert dt._apply_windows_acl("C:/fake/token") is False
    assert "icacls not found on PATH" in capsys.readouterr().out


def test_apply_windows_acl_handles_timeout(monkeypatch, capsys):
    """Lines 99-104: icacls hangs -> TimeoutExpired -> WARNING + False."""
    monkeypatch.setattr(getpass, "getuser", lambda: "testuser")

    def _boom_run(cmd, **k):
        raise subprocess.TimeoutExpired(cmd, 5.0)

    monkeypatch.setattr(subprocess, "run", _boom_run)
    assert dt._apply_windows_acl("C:/fake/token") is False
    assert "timed out" in capsys.readouterr().out


# ───────────────────────────────────────────────────────────────────────
# _cleanup_partial_writes — raced unlink swallow (lines 119-120)
# ───────────────────────────────────────────────────────────────────────


def test_cleanup_partial_writes_swallows_unlink_oserror(tmp_path, monkeypatch):
    """Lines 119-120: another process racing the unlink is harmless."""
    stray = tmp_path / ".dashboard_token.tmp.9999"
    stray.write_text("partial")

    def _boom_unlink(self, *a, **k):
        raise OSError("raced by another process")

    monkeypatch.setattr(Path, "unlink", _boom_unlink)
    dt._cleanup_partial_writes(tmp_path)  # must not raise


# ───────────────────────────────────────────────────────────────────────
# _verify_mode_self_heal — POSIX branch (lines 147-160)
# ───────────────────────────────────────────────────────────────────────


def test_verify_mode_self_heal_posix_drift_chmod_ok(tmp_path, monkeypatch, capsys):
    """Lines 147-148,151-158: POSIX mode drifted -> WARNING + chmod back to 0600."""
    monkeypatch.setattr(dt.sys, "platform", "linux")
    token_path = tmp_path / ".dashboard_token"
    token_path.write_text("x")

    real_stat = os.stat

    def _fake_stat(p, *a, **k):
        if str(p) == str(token_path):
            return types.SimpleNamespace(st_mode=0o644)  # drift
        return real_stat(p, *a, **k)

    monkeypatch.setattr(os, "stat", _fake_stat)

    chmod_calls = []
    real_chmod = os.chmod

    def _rec_chmod(p, mode, *a, **k):
        if str(p) == str(token_path):
            chmod_calls.append((str(p), mode))
            return None
        return real_chmod(p, mode, *a, **k)

    monkeypatch.setattr(os, "chmod", _rec_chmod)
    dt._verify_mode_self_heal(token_path)

    assert chmod_calls == [(str(token_path), 0o600)]
    assert "mode drifted" in capsys.readouterr().out


def test_verify_mode_self_heal_posix_no_drift(tmp_path, monkeypatch, capsys):
    """Line 151 False branch: mode already 0600 -> no warning, no chmod."""
    monkeypatch.setattr(dt.sys, "platform", "linux")
    token_path = tmp_path / ".dashboard_token"
    token_path.write_text("x")

    real_stat = os.stat

    def _fake_stat(p, *a, **k):
        if str(p) == str(token_path):
            return types.SimpleNamespace(st_mode=0o600)  # no drift
        return real_stat(p, *a, **k)

    monkeypatch.setattr(os, "stat", _fake_stat)

    real_chmod = os.chmod

    def _guard_chmod(p, mode, *a, **k):
        if str(p) == str(token_path):
            raise AssertionError("chmod MUST NOT run when mode is already 0600")
        return real_chmod(p, mode, *a, **k)

    monkeypatch.setattr(os, "chmod", _guard_chmod)
    dt._verify_mode_self_heal(token_path)
    assert "mode drifted" not in capsys.readouterr().out


def test_verify_mode_self_heal_posix_stat_oserror(tmp_path, monkeypatch):
    """Lines 149-150: os.stat raising OSError (missing file) -> early return."""
    monkeypatch.setattr(dt.sys, "platform", "linux")
    missing = tmp_path / ".dashboard_token"  # never created -> os.stat raises
    dt._verify_mode_self_heal(missing)  # must not raise


def test_verify_mode_self_heal_posix_chmod_oserror(tmp_path, monkeypatch, capsys):
    """Lines 159-160: self-heal chmod raises OSError -> final WARNING logged."""
    monkeypatch.setattr(dt.sys, "platform", "linux")
    token_path = tmp_path / ".dashboard_token"
    token_path.write_text("x")

    real_stat = os.stat

    def _fake_stat(p, *a, **k):
        if str(p) == str(token_path):
            return types.SimpleNamespace(st_mode=0o644)  # drift
        return real_stat(p, *a, **k)

    monkeypatch.setattr(os, "stat", _fake_stat)

    real_chmod = os.chmod

    def _boom_chmod(p, mode, *a, **k):
        if str(p) == str(token_path):
            raise OSError("chmod denied by kernel")
        return real_chmod(p, mode, *a, **k)

    monkeypatch.setattr(os, "chmod", _boom_chmod)
    dt._verify_mode_self_heal(token_path)  # must not raise
    assert "chmod 0600 failed" in capsys.readouterr().out


# ───────────────────────────────────────────────────────────────────────
# _ensure_dashboard_token — unreadable existing token (lines 206-214)
# ───────────────────────────────────────────────────────────────────────


def test_ensure_token_unreadable_backs_up_and_regenerates(tmp_path, monkeypatch, capsys):
    """Lines 206-214: existing token unreadable (read_text OSError) -> backup + regen."""
    token_path = tmp_path / ".dashboard_token"
    token_path.write_text("stale-unreadable")  # exists -> not the missing-file path

    real_read_text = Path.read_text

    def _boom_read_text(self, *a, **k):
        if str(self) == str(token_path):
            raise OSError("permission denied reading token")
        return real_read_text(self, *a, **k)

    monkeypatch.setattr(Path, "read_text", _boom_read_text)

    token = dt._ensure_dashboard_token(tmp_path)

    # A fresh valid token was generated and returned.
    assert dt._verify_token_shape(token)
    # On-disk token matches (read via bytes to dodge the patched read_text).
    assert token_path.read_bytes().decode().rstrip("\r\n") == token
    # The corrupt original was preserved as forensic evidence.
    backups = list(tmp_path.glob(".dashboard_token.corrupt.*"))
    assert len(backups) == 1
    assert "unreadable" in capsys.readouterr().out


# ───────────────────────────────────────────────────────────────────────
# _backup_corrupt_token — os.replace fails -> copy-then-unlink (lines 245-256)
# ───────────────────────────────────────────────────────────────────────


def test_backup_corrupt_token_copy_fallback_succeeds(tmp_path, monkeypatch, capsys):
    """Lines 245-254: os.replace fails -> copy-then-unlink fallback keeps evidence."""
    token_path = tmp_path / ".dashboard_token"
    token_path.write_bytes(b"corrupt-bytes")

    def _boom_replace(src, dst, *a, **k):
        raise OSError("cross-device rename not permitted")

    monkeypatch.setattr(os, "replace", _boom_replace)
    dt._backup_corrupt_token(token_path)

    assert not token_path.exists()
    backups = list(tmp_path.glob(".dashboard_token.corrupt.*"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == b"corrupt-bytes"
    assert "backup rename failed" in capsys.readouterr().out


def test_backup_corrupt_token_copy_fallback_also_fails(tmp_path, monkeypatch, capsys):
    """Lines 255-256: os.replace fails AND the copy fails -> final WARNING logged."""
    token_path = tmp_path / ".dashboard_token"
    token_path.write_bytes(b"corrupt-bytes")

    def _boom_replace(src, dst, *a, **k):
        raise OSError("cross-device rename not permitted")

    monkeypatch.setattr(os, "replace", _boom_replace)

    real_read_bytes = Path.read_bytes

    def _boom_read_bytes(self, *a, **k):
        if str(self) == str(token_path):
            raise OSError("read failed during copy fallback")
        return real_read_bytes(self, *a, **k)

    monkeypatch.setattr(Path, "read_bytes", _boom_read_bytes)
    dt._backup_corrupt_token(token_path)  # must not raise
    assert "backup also failed via copy" in capsys.readouterr().out
