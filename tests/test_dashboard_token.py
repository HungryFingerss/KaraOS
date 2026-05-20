"""tests/test_dashboard_token.py — P0.S2 dashboard auth token (Python side).

Covers D1 (token generation, 6 tests including Plan v2 §3.13 corruption
recovery + atomic-write invariant), D4 partial (1 — file-read invariant
end is in middleware tests), D6 partial (1 — wipe_all preservation), and
D7 POSIX (2 — mode 0600 + self-heal). Windows D7 (icacls invocation + failure
recovery) lives in `tests/test_dashboard_token_windows.py`.

Test plan locked at `tests/p0_s2_plan_v1.md` §2 + Plan v2 §3.
"""
from __future__ import annotations

import os
import stat
import sys
import time
from pathlib import Path

import pytest


pytestmark = [
    # POSIX-mode tests cannot run on Windows because os.chmod has different
    # semantics; gate them per-test below where applicable.
]


# ───────────────────────────────────────────────────────────────────────
# D1 — token generation (6 tests; Plan v2 §3.13 adds 2 corruption tests)
# ───────────────────────────────────────────────────────────────────────


def test_pipeline_boot_creates_token_if_missing(tmp_path):
    """D1 test 1 — POSIX boot path: missing `.dashboard_token` → generate.

    Calls `_ensure_dashboard_token(tmp_path)`, asserts:
      - `.dashboard_token` exists
      - content length == 43 (secrets.token_urlsafe(32) shape)
      - mode is 0o600 (POSIX gate; Windows-specific test in companion file)
      - `.dashboard_auth_url` also created with valid URL content
    """
    from core.dashboard_token import _ensure_dashboard_token

    token = _ensure_dashboard_token(tmp_path)
    token_path = tmp_path / ".dashboard_token"
    assert token_path.exists()
    content = token_path.read_text(encoding="utf-8").rstrip("\r\n")
    assert len(content) == 43, (
        f"token MUST be 43 urlsafe chars (secrets.token_urlsafe(32) shape); "
        f"got {len(content)}"
    )
    assert content == token, "returned token MUST match on-disk content"

    # POSIX-only mode check
    if sys.platform != "win32":
        mode = os.stat(token_path).st_mode & 0o777
        assert mode == 0o600, f"token file MUST be mode 0o600; got {oct(mode)}"

    # Auth URL also written
    url_path = tmp_path / ".dashboard_auth_url"
    assert url_path.exists()
    url_content = url_path.read_text(encoding="utf-8").rstrip("\r\n")
    assert url_content == f"http://127.0.0.1:3000/api/auth?token={token}"


def test_pipeline_boot_preserves_existing_token(tmp_path):
    """D1 test 2 — existing valid token preserved on subsequent boot."""
    from core.dashboard_token import _ensure_dashboard_token

    token_path = tmp_path / ".dashboard_token"
    # 43-char valid urlsafe token
    known_token = "A" * 43
    token_path.write_text(known_token, encoding="utf-8")
    if sys.platform != "win32":
        os.chmod(token_path, 0o600)

    returned = _ensure_dashboard_token(tmp_path)
    assert returned == known_token, "valid existing token MUST be returned verbatim"
    assert token_path.read_text(encoding="utf-8").rstrip("\r\n") == known_token


def test_token_is_high_entropy(tmp_path):
    """D1 test 3 — 100 fresh tokens, no collisions, urlsafe alphabet."""
    from core.dashboard_token import _ensure_dashboard_token
    import re as _re

    seen = set()
    urlsafe = _re.compile(r"^[A-Za-z0-9_-]+$")
    for i in range(100):
        d = tmp_path / f"f{i}"
        d.mkdir()
        t = _ensure_dashboard_token(d)
        assert urlsafe.match(t), f"token MUST be urlsafe; got {t!r}"
        assert t not in seen, f"collision at iteration {i}: {t!r}"
        seen.add(t)
    assert len(seen) == 100


def test_token_creation_is_atomic_replace(tmp_path, monkeypatch):
    """D1 test 4 — crash mid-write leaves no partial canonical file and no
    `.tmp` artifact survives the next clean boot.

    Strategy: monkeypatch `os.replace` to raise mid-write, then on a second
    boot verify `_cleanup_partial_writes` removes the orphan tmp + a fresh
    token is generated cleanly.
    """
    from core import dashboard_token as _dt

    # 1st pass: simulate crash by making os.replace fail
    def _raise(*a, **kw):
        raise OSError("simulated crash")

    monkeypatch.setattr(_dt.os, "replace", _raise)
    with pytest.raises(OSError):
        _dt._ensure_dashboard_token(tmp_path)
    # Canonical file should NOT exist; tmp artifact MAY exist
    assert not (tmp_path / ".dashboard_token").exists()

    # 2nd pass: restore os.replace and boot cleanly → tmp swept + fresh token
    monkeypatch.undo()
    token = _dt._ensure_dashboard_token(tmp_path)
    assert (tmp_path / ".dashboard_token").exists()
    # No tmp artifacts remain
    tmp_artifacts = list(tmp_path.glob(".dashboard_token.tmp.*"))
    assert tmp_artifacts == [], (
        f"_cleanup_partial_writes should have swept .tmp.* artifacts; "
        f"found: {tmp_artifacts}"
    )
    assert len(token) == 43


def test_corrupt_token_file_triggers_regenerate_and_backup(tmp_path, capsys):
    """D1 test 5 (Plan v2 §3.13) — corrupt token → backup + regenerate + WARNING."""
    from core.dashboard_token import _ensure_dashboard_token

    token_path = tmp_path / ".dashboard_token"
    # Write garbage that fails shape validation
    garbage = "not-a-43-char-urlsafe-token"
    token_path.write_text(garbage, encoding="utf-8")
    if sys.platform != "win32":
        os.chmod(token_path, 0o600)

    new_token = _ensure_dashboard_token(tmp_path)
    # Backup file created with .corrupt.<ts> suffix preserving original content
    backups = list(tmp_path.glob(".dashboard_token.corrupt.*"))
    assert len(backups) == 1, (
        f"corruption MUST create exactly one backup; found {backups}"
    )
    assert backups[0].read_text(encoding="utf-8") == garbage, (
        "backup MUST preserve original (garbage) content as forensic evidence"
    )
    # Fresh token has valid shape
    assert len(new_token) == 43
    assert token_path.read_text(encoding="utf-8").rstrip("\r\n") == new_token
    # WARNING log emitted
    out = capsys.readouterr().out
    assert "WARNING" in out
    assert "shape validation" in out


def test_valid_token_passes_shape_validation(tmp_path, capsys):
    """D1 test 6 (Plan v2 §3.13 complement) — valid token leaves no backup,
    no WARNING about shape, content unchanged.
    """
    from core.dashboard_token import _ensure_dashboard_token

    token_path = tmp_path / ".dashboard_token"
    # 43 urlsafe chars
    valid = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQ"
    assert len(valid) == 43
    token_path.write_text(valid, encoding="utf-8")
    if sys.platform != "win32":
        os.chmod(token_path, 0o600)

    returned = _ensure_dashboard_token(tmp_path)
    assert returned == valid
    backups = list(tmp_path.glob(".dashboard_token.corrupt.*"))
    assert backups == [], (
        f"valid token MUST NOT trigger backup; found {backups}"
    )
    out = capsys.readouterr().out
    assert "shape validation" not in out


# ───────────────────────────────────────────────────────────────────────
# D4 — file-read invariant (1 Python-side test; rest in middleware tests)
# ───────────────────────────────────────────────────────────────────────


def test_ensure_dashboard_token_reads_file_on_every_call(tmp_path):
    """D4 (Python-side) — boot helper re-reads `.dashboard_token` on every
    invocation; no module-scope caching. Mutating the on-disk file between
    calls must reflect in the next call's return value.

    This is the Python-side complement to the middleware.ts file-read
    invariant in `test_dashboard_middleware.py`.
    """
    from core.dashboard_token import _ensure_dashboard_token

    # Generate token 1
    t1 = _ensure_dashboard_token(tmp_path)
    # Manually replace with a different valid token directly on disk
    new_valid = "X" * 43
    (tmp_path / ".dashboard_token").write_text(new_valid, encoding="utf-8")
    if sys.platform != "win32":
        os.chmod(tmp_path / ".dashboard_token", 0o600)

    t2 = _ensure_dashboard_token(tmp_path)
    assert t2 == new_valid, (
        "boot helper MUST re-read the on-disk file every call — cached "
        "return value would silently mask manual token-replacement workflows"
    )
    assert t1 != t2


# ───────────────────────────────────────────────────────────────────────
# D6 — factory-reset preservation (1 Python-side test)
# ───────────────────────────────────────────────────────────────────────


def test_wipe_all_preserves_dashboard_token(tmp_path, monkeypatch):
    """D6 test 22 — `core.db.wipe_all()` MUST preserve `.dashboard_token`
    and `.dashboard_auth_url`. Re-issuing auth URL on every reset is hostile
    UX (Plan v1 §1.P4 + comment block in core/db.py).
    """
    from core import db as _db_mod
    import sqlite3

    faces_dir = tmp_path
    # Redirect every wipe target to tmp_path
    monkeypatch.setattr(_db_mod, "DB_PATH", faces_dir / "faces.db")
    monkeypatch.setattr(_db_mod, "FAISS_INDEX_PATH", faces_dir / "faiss.index")
    monkeypatch.setattr(_db_mod, "BRAIN_DB_PATH", faces_dir / "brain.db")
    monkeypatch.setattr(_db_mod, "GRAPH_DB_PATH", faces_dir / "brain_graph")
    monkeypatch.setattr(_db_mod, "FACES_DIR", faces_dir)
    monkeypatch.setattr(_db_mod, "ENROLL_REQUEST_FILE", faces_dir / "enroll_req.tmp")
    monkeypatch.setattr(_db_mod, "ENROLL_RESULT_FILE", faces_dir / "enroll_res.tmp")
    monkeypatch.setattr(_db_mod, "RESET_REQUEST_FILE", faces_dir / "reset_req.tmp")
    monkeypatch.setattr(_db_mod, "RESET_RESULT_FILE", faces_dir / "reset_res.tmp")

    # Seed: a valid token + a dummy faces.db artifact
    token = "T" * 43
    (faces_dir / ".dashboard_token").write_text(token, encoding="utf-8")
    (faces_dir / ".dashboard_auth_url").write_text(
        f"http://127.0.0.1:3000/api/auth?token={token}", encoding="utf-8"
    )
    # Touch a faces.db so we can verify deletion fires
    conn = sqlite3.connect(str(faces_dir / "faces.db"))
    conn.execute("CREATE TABLE marker (id INT)")
    conn.commit()
    conn.close()
    assert (faces_dir / "faces.db").exists()

    _db_mod.wipe_all()

    # P0.S2 preservation invariant
    assert (faces_dir / ".dashboard_token").exists(), (
        "wipe_all MUST preserve .dashboard_token (P0.S2 invariant)"
    )
    assert (faces_dir / ".dashboard_token").read_text(encoding="utf-8") == token
    assert (faces_dir / ".dashboard_auth_url").exists(), (
        "wipe_all MUST preserve .dashboard_auth_url (P0.S2 invariant)"
    )
    # faces.db actually deleted
    assert not (faces_dir / "faces.db").exists()


# ───────────────────────────────────────────────────────────────────────
# D7 POSIX — mode 0600 + self-heal (2 tests; Windows in companion file)
# ───────────────────────────────────────────────────────────────────────


@pytest.mark.skipif(sys.platform == "win32",
                    reason="POSIX chmod semantics — Windows ACL test lives in companion file")
def test_token_file_mode_is_0600_after_creation(tmp_path):
    """D7 test 25 — fresh token file has mode 0o600 immediately after creation."""
    from core.dashboard_token import _ensure_dashboard_token

    _ensure_dashboard_token(tmp_path)
    mode = os.stat(tmp_path / ".dashboard_token").st_mode & 0o777
    assert mode == 0o600, f"token file MUST be mode 0o600; got {oct(mode)}"


@pytest.mark.skipif(sys.platform == "win32",
                    reason="POSIX chmod semantics — Windows ACL test lives in companion file")
def test_token_file_mode_self_heals_on_boot_check(tmp_path, capsys):
    """D7 test 26 — drift in mode (e.g., chmod 0644) is detected at boot and
    self-healed to 0o600 with a WARNING log.
    """
    from core.dashboard_token import _ensure_dashboard_token

    _ensure_dashboard_token(tmp_path)
    token_path = tmp_path / ".dashboard_token"
    # Drift the mode manually
    os.chmod(token_path, 0o644)
    assert (os.stat(token_path).st_mode & 0o777) == 0o644

    _ensure_dashboard_token(tmp_path)
    mode = os.stat(token_path).st_mode & 0o777
    assert mode == 0o600, (
        f"self-heal MUST restore 0o600 on mode drift; got {oct(mode)}"
    )
    out = capsys.readouterr().out
    assert "WARNING" in out
    assert "mode drifted" in out


# ───────────────────────────────────────────────────────────────────────
# Helper: _verify_token_shape unit invariants (covered indirectly above)
# ───────────────────────────────────────────────────────────────────────


def test_verify_token_shape_accepts_valid_urlsafe_43():
    from core.dashboard_token import _verify_token_shape
    assert _verify_token_shape("A" * 43)
    assert _verify_token_shape("a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8s9T0u1V")
    # Underscore + hyphen allowed (urlsafe alphabet)
    assert _verify_token_shape("_" * 43)
    assert _verify_token_shape("-" * 43)


def test_verify_token_shape_rejects_invalid():
    from core.dashboard_token import _verify_token_shape
    # Too short
    assert not _verify_token_shape("A" * 42)
    # Too long
    assert not _verify_token_shape("A" * 44)
    # Empty
    assert not _verify_token_shape("")
    # Contains forbidden char
    assert not _verify_token_shape("A" * 42 + "$")
    # Contains whitespace
    assert not _verify_token_shape("A" * 42 + " ")
