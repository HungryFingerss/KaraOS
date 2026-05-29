"""core/dashboard_token.py — P0.S2 dashboard authentication token management.

Generates and self-heals a single-user authentication token used by the
Next.js dashboard's middleware + `/api/auth` route. Token is written to
`faces/.dashboard_token` (mode 0600, owner-only ACL on Windows via icacls)
and surfaced as a one-shot URL in `faces/.dashboard_auth_url` (clicked
once by the user; deleted by `/api/auth` on first successful validation).

Plan v2 §3.13 corruption recovery: on every boot we shape-validate the
existing token. Anything that doesn't match `^[A-Za-z0-9_-]{43}$` is
backed up as `.dashboard_token.corrupt.<ts>` and regenerated so the
pipeline never blocks on filesystem corruption.

Public entry point: `_ensure_dashboard_token(faces_dir)`.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import getpass
import os
import re
import secrets
import subprocess
import sys
import time
from pathlib import Path


# Token shape: `secrets.token_urlsafe(32)` returns exactly 43 urlsafe chars.
# Locked at Plan v2 §3.13; the regex is the corruption-recovery shape gate.
_VALID_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{43}$")


def _verify_token_shape(content: str) -> bool:
    """Token shape from secrets.token_urlsafe(32) is exactly 43 urlsafe chars."""
    return bool(_VALID_TOKEN_RE.match(content))


def _atomic_write_secret(path: Path, content: str) -> None:
    """Write content to path atomically: write to `.tmp.<pid>` then rename.

    Crash mid-write leaves the tmp artifact (cleaned up by
    `_cleanup_partial_writes` at next boot); the canonical path is
    either present-and-valid or absent. Sets mode 0600 on the tmp file
    BEFORE rename so the canonical file is never world-readable.
    """
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    # Write + flush + fsync the tmp file, then rename.
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(content)
        fh.flush()
        try:
            os.fsync(fh.fileno())
        except OSError:
            pass  # CLEANUP: fsync may fail on some filesystems (tmpfs, FAT); not fatal
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass  # CLEANUP: chmod on Windows is partial; _apply_windows_acl below restricts properly
    os.replace(tmp, path)


def _apply_windows_acl(path: str) -> bool:
    """Restrict path to current user only via icacls. Returns True on success.

    Best-effort: returns False + logs WARNING if icacls fails or is unavailable.
    Plan v1 §1.P3 locked design — see spec for full rationale.
    """
    import subprocess  # function-scope re-import per Plan v2 Q5-C — string-form patches survive future refactors
    try:
        username = getpass.getuser()
        result = subprocess.run(
            ["icacls", path, "/inheritance:r", "/grant:r", f"{username}:F"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5.0,  # icacls should never take this long; bail on hang
        )
        if result.returncode == 0:
            return True
        print(
            f"[Dashboard] WARNING: icacls failed to restrict {path!r} "
            f"(rc={result.returncode}); file may be readable by other Windows accounts. "
            f"stdout: {result.stdout.strip()!r}, stderr: {result.stderr.strip()!r}",
            flush=True,
        )
        return False
    except FileNotFoundError:
        print(
            f"[Dashboard] WARNING: icacls not found on PATH; cannot restrict "
            f"{path!r} on Windows. Token file is mode 0600 (Python chmod) but "
            f"other Windows accounts may still have inherited permissions.",
            flush=True,
        )
        return False
    except subprocess.TimeoutExpired:
        print(
            f"[Dashboard] WARNING: icacls timed out restricting {path!r}",
            flush=True,
        )
        return False


def _restrict_to_owner(path: str) -> None:
    """Apply 0600-equivalent restriction. POSIX uses chmod; Windows uses icacls."""
    os.chmod(path, 0o600)  # POSIX: real effect. Windows: read-only flag only.
    if sys.platform == "win32":
        _apply_windows_acl(path)


def _cleanup_partial_writes(faces_dir: Path) -> None:
    """Remove any `.dashboard_token.tmp.*` artifacts left by a crashed write."""
    for tmp in faces_dir.glob(".dashboard_token.tmp.*"):
        try:
            tmp.unlink()
        except OSError:
            pass  # CLEANUP: another process may have raced us; harmless


def _write_auth_url(token: str, faces_dir: Path) -> None:
    """Write the one-shot `.dashboard_auth_url` file (mode 0600).

    Contains the click-once URL that includes the token in the query
    string. `/api/auth` deletes this file on first successful validation.
    Subsequent boots do NOT regenerate it — only present after a fresh
    token generation event.
    """
    url_path = faces_dir / ".dashboard_auth_url"
    url = f"http://127.0.0.1:3000/api/auth?token={token}"
    _atomic_write_secret(url_path, url)
    _restrict_to_owner(str(url_path))


def _verify_mode_self_heal(path: Path) -> None:
    """Verify token file is mode 0600 (POSIX) / restricted-ACL (Windows).

    If POSIX mode has drifted from 0o600, log WARNING + chmod back to 0600.
    On Windows, defensively re-run icacls every boot (idempotent).
    """
    if sys.platform == "win32":
        # icacls is cheap; re-apply every boot to self-heal any drift.
        _apply_windows_acl(str(path))
        return
    try:
        current_mode = os.stat(path).st_mode & 0o777
    except OSError:
        return
    if current_mode != 0o600:
        print(
            f"[Dashboard] WARNING: token file mode drifted to {oct(current_mode)} "
            f"(expected 0o600); self-healing via chmod.",
            flush=True,
        )
        try:
            os.chmod(path, 0o600)
        except OSError as e:
            print(
                f"[Dashboard] WARNING: chmod 0600 failed on {path}: {e!r}",
                flush=True,
            )


def _ensure_dashboard_token(faces_dir: Path) -> str:
    """Pipeline boot entry point — guarantee a valid token exists on disk.

    Steps:
      1. Cleanup any partial `.tmp.<pid>` writes from a prior crash.
      2. If `.dashboard_token` missing → generate + write atomic + restrict
         + write one-shot auth URL + stdout banner. Return the token.
      3. If `.dashboard_token` present → read + shape-validate. On invalid
         content (empty / garbage / truncated): backup as
         `.dashboard_token.corrupt.<ts>`, regenerate, write new auth URL,
         WARNING log. On valid content: self-heal file mode (drift check).
         Return the token.

    Returns the token content (43-char urlsafe string).
    """
    faces_dir = Path(faces_dir)
    faces_dir.mkdir(parents=True, exist_ok=True)
    token_path = faces_dir / ".dashboard_token"

    _cleanup_partial_writes(faces_dir)

    def _generate_and_publish() -> str:
        new_token = secrets.token_urlsafe(32)
        _atomic_write_secret(token_path, new_token)
        _restrict_to_owner(str(token_path))
        _write_auth_url(new_token, faces_dir)
        print(
            "[Dashboard] First-launch auth URL written to "
            "faces/.dashboard_auth_url — click once, then this file will be "
            "auto-deleted after first successful auth.",
            flush=True,
        )
        return new_token

    if not token_path.exists():
        return _generate_and_publish()

    # Token file exists. Read + shape-validate.
    try:
        content = token_path.read_text(encoding="utf-8").rstrip("\r\n")
    except OSError as e:
        # Unreadable file is the corruption case writ large. Back it up and regen.
        print(
            f"[Dashboard] WARNING: existing .dashboard_token unreadable ({e!r}); "
            f"backing up and regenerating.",
            flush=True,
        )
        _backup_corrupt_token(token_path)
        return _generate_and_publish()

    if not _verify_token_shape(content):
        print(
            f"[Dashboard] WARNING: existing .dashboard_token failed shape "
            f"validation (len={len(content)}, expected 43 urlsafe chars); "
            f"backing up as .dashboard_token.corrupt.<ts> and regenerating. "
            f"Cookies tied to the previous token will need to re-auth via the "
            f"new .dashboard_auth_url.",
            flush=True,
        )
        _backup_corrupt_token(token_path)
        return _generate_and_publish()

    # Valid token — self-heal mode drift.
    _verify_mode_self_heal(token_path)
    return content


def _backup_corrupt_token(token_path: Path) -> None:
    """Rename corrupt token to `.dashboard_token.corrupt.<unix_ts>`.

    Preserves the corrupt content as forensic evidence (Plan v2 §3.13
    rationale: if filesystem corruption is widespread, the user or
    future-architect can inspect what happened). The `.corrupt.<ts>`
    suffix excludes the file from any future regeneration check — only
    the canonical filename matters for boot logic.
    """
    backup = token_path.with_name(f"{token_path.name}.corrupt.{int(time.time())}")
    try:
        os.replace(token_path, backup)
    except OSError as e:
        # If rename fails, fall back to copy-then-unlink so we at least keep evidence.
        print(
            f"[Dashboard] WARNING: backup rename failed ({e!r}); "
            f"falling back to copy-then-unlink.",
            flush=True,
        )
        try:
            backup.write_bytes(token_path.read_bytes())
            token_path.unlink()
        except OSError as e2:
            print(
                f"[Dashboard] WARNING: backup also failed via copy ({e2!r}); "
                f"corrupt file may be lost.",
                flush=True,
            )
