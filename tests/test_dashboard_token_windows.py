"""tests/test_dashboard_token_windows.py — P0.S2 D7 Windows ACL tests.

D7 test 27 (icacls invocation) + D7 test 28 (icacls failure recovery).
Both skip on POSIX. Patches use string-form per Plan v2 Q5-C:
`monkeypatch.setattr('subprocess.run', spy)` survives the function-scope
`import subprocess` inside `_apply_windows_acl`.
"""
from __future__ import annotations

import getpass
import sys

import pytest


pytestmark = pytest.mark.skipif(
    sys.platform != "win32",
    reason="Windows-only — icacls is Windows-specific",
)


def test_windows_icacls_invocation(monkeypatch, tmp_path):
    """D7 test 27 — `_apply_windows_acl` invokes icacls with the locked
    arg shape: ['icacls', path, '/inheritance:r', '/grant:r', f'{user}:F']
    AND kwargs `check=False`, `capture_output=True`, `timeout=5.0`.

    Plan v2 Q5-C: string-form `monkeypatch.setattr('subprocess.run', _spy)`
    so the patch survives the function-scope `import subprocess` inside
    `_apply_windows_acl`.
    """
    import subprocess as _sp  # for CompletedProcess construction; NOT the patched site

    spy_calls = []

    def _spy(*args, **kwargs):
        spy_calls.append((args, kwargs))
        return _sp.CompletedProcess(
            args=args[0], returncode=0, stdout="processed", stderr=""
        )

    monkeypatch.setattr("subprocess.run", _spy)

    from core.dashboard_token import _apply_windows_acl

    fake_path = str(tmp_path / "fake_token")
    result = _apply_windows_acl(fake_path)
    assert result is True

    assert len(spy_calls) == 1
    args, kwargs = spy_calls[0]
    cmd = args[0]
    # Locked argv shape per Plan v1 §2 test 27:
    #   ['icacls', path, '/inheritance:r', '/grant:r', f'{user}:F']
    assert cmd[0] == "icacls"
    assert cmd[1] == fake_path
    assert cmd[2:4] == ["/inheritance:r", "/grant:r"]
    assert cmd[4] == f"{getpass.getuser()}:F"
    assert len(cmd) == 5, f"argv shape locked at 5 elements; got {len(cmd)}: {cmd}"
    assert kwargs.get("check") is False
    assert kwargs.get("capture_output") is True
    assert kwargs.get("timeout") == 5.0


def test_windows_icacls_failure_logs_warning_returns_false(monkeypatch, tmp_path, capsys):
    """D7 test 28 — icacls returncode=1 (access denied / quirks) → helper
    returns False + emits WARNING with stdout/stderr captured. Pipeline
    does NOT crash; the user is told the limitation honestly.
    """
    import subprocess as _sp

    def _spy(*args, **kwargs):
        return _sp.CompletedProcess(
            args=args[0],
            returncode=1,
            stdout="",
            stderr="access denied",
        )

    monkeypatch.setattr("subprocess.run", _spy)

    from core.dashboard_token import _apply_windows_acl

    fake_path = str(tmp_path / "fake_token")
    result = _apply_windows_acl(fake_path)
    assert result is False, "icacls returncode != 0 → helper returns False"

    out = capsys.readouterr().out
    assert "WARNING" in out
    assert "icacls failed" in out
    assert "access denied" in out, (
        "stderr from icacls MUST be captured in WARNING for forensic value"
    )
