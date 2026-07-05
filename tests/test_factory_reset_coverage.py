# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors
"""100% coverage for tools/factory_reset.py — standalone factory reset CLI (P0.S11).
Part of the coverage-to-100 campaign (every line exercised or pragma'd)."""

from __future__ import annotations

import importlib
import json
import sys
import time
from pathlib import Path

import pytest

# Import the CLI exactly like the sibling P0.S11 suite: tools/ on sys.path,
# then `import factory_reset`. The coverage file measured is the same
# `tools/factory_reset.py` regardless of the module's dotted name.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_TOOLS_DIR = _REPO_ROOT / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import factory_reset as _fr  # noqa: E402


# ───────────────────────────────────────────────────────────────────────
# Helper — redirect factory_reset's `from core.db import` path constants at
# a tmp faces dir so main()'s enumeration + token-loop stay hermetic.
# ───────────────────────────────────────────────────────────────────────


def _redirect_fr_paths(monkeypatch, tmp_path: Path) -> Path:
    faces = tmp_path / "faces"
    faces.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(_fr, "DB_PATH", faces / "faces.db")
    monkeypatch.setattr(_fr, "FAISS_INDEX_PATH", faces / "faiss.index")
    monkeypatch.setattr(_fr, "BRAIN_DB_PATH", faces / "brain.db")
    monkeypatch.setattr(_fr, "GRAPH_DB_PATH", faces / "brain_graph")
    monkeypatch.setattr(_fr, "FACES_DIR", faces)
    return faces


# ───────────────────────────────────────────────────────────────────────
# _is_pipeline_live — happy paths + the malformed-state except (lines 69-70)
# ───────────────────────────────────────────────────────────────────────


def test_is_pipeline_live_missing_state_file_returns_false(tmp_path, monkeypatch):
    """Line 62-63 — no state.json at all -> not live (safe default)."""
    faces = tmp_path / "faces"
    faces.mkdir()
    monkeypatch.setattr(_fr, "FACES_DIR", faces)
    assert _fr._is_pipeline_live() is False


def test_is_pipeline_live_fresh_state_returns_true(tmp_path, monkeypatch):
    """Line 68 (True branch) — updated_at within 10s -> pipeline is live."""
    faces = tmp_path / "faces"
    faces.mkdir()
    (faces / "state.json").write_text(
        json.dumps({"updated_at": time.time()}), encoding="utf-8"
    )
    monkeypatch.setattr(_fr, "FACES_DIR", faces)
    assert _fr._is_pipeline_live() is True


def test_is_pipeline_live_stale_state_returns_false(tmp_path, monkeypatch):
    """Line 68 (False branch) — updated_at older than 10s -> not live."""
    faces = tmp_path / "faces"
    faces.mkdir()
    (faces / "state.json").write_text(
        json.dumps({"updated_at": time.time() - 30.0}), encoding="utf-8"
    )
    monkeypatch.setattr(_fr, "FACES_DIR", faces)
    assert _fr._is_pipeline_live() is False


def test_is_pipeline_live_malformed_json_returns_false(tmp_path, monkeypatch):
    """Lines 69-70 — a state.json that isn't valid JSON raises
    json.JSONDecodeError; the except handler swallows it and returns False."""
    faces = tmp_path / "faces"
    faces.mkdir()
    (faces / "state.json").write_text("{ this is not valid json", encoding="utf-8")
    monkeypatch.setattr(_fr, "FACES_DIR", faces)
    assert _fr._is_pipeline_live() is False


def test_is_pipeline_live_non_float_updated_at_returns_false(tmp_path, monkeypatch):
    """Lines 69-70 (ValueError arm) — a non-float updated_at makes
    `float(...)` raise ValueError, caught by the same except -> False."""
    faces = tmp_path / "faces"
    faces.mkdir()
    (faces / "state.json").write_text(
        json.dumps({"updated_at": "not-a-number"}), encoding="utf-8"
    )
    monkeypatch.setattr(_fr, "FACES_DIR", faces)
    assert _fr._is_pipeline_live() is False


# ───────────────────────────────────────────────────────────────────────
# _enumerate_targets — both include-token branches (lines 99-101)
# ───────────────────────────────────────────────────────────────────────


def test_enumerate_targets_preserves_token_by_default(tmp_path, monkeypatch):
    """include_dashboard_token=False -> token files land in `preserved`, not
    `targets` (the P0.S2 preservation default)."""
    faces = _redirect_fr_paths(monkeypatch, tmp_path)
    targets, preserved = _fr._enumerate_targets(include_dashboard_token=False)
    token = str(faces / ".dashboard_token")
    auth = str(faces / ".dashboard_auth_url")
    assert token in preserved and auth in preserved
    assert token not in targets and auth not in targets


def test_enumerate_targets_include_token_moves_to_delete(tmp_path, monkeypatch):
    """Lines 99-101 — include_dashboard_token=True extends `targets` with the
    two token files and empties `preserved`."""
    faces = _redirect_fr_paths(monkeypatch, tmp_path)
    targets, preserved = _fr._enumerate_targets(include_dashboard_token=True)
    token = str(faces / ".dashboard_token")
    auth = str(faces / ".dashboard_auth_url")
    assert token in targets and auth in targets
    assert preserved == []


# ───────────────────────────────────────────────────────────────────────
# main() — dry-run / liveness-refusal / success / error exit codes
# ───────────────────────────────────────────────────────────────────────


def test_main_dry_run_returns_zero_deletes_nothing(tmp_path, monkeypatch, capsys):
    """Default (no --confirm) enters dry-run: exit 0, prints DRY RUN, and
    never touches wipe_all()."""
    faces = _redirect_fr_paths(monkeypatch, tmp_path)
    (faces / "faces.db").write_text("dummy", encoding="utf-8")

    # If wipe_all were ever called in dry-run that's a bug — make it explode.
    def _must_not_run():  # pragma: no cover  # only runs if dry-run regresses
        raise AssertionError("wipe_all must NOT be called in dry-run mode")

    monkeypatch.setattr(_fr, "wipe_all", _must_not_run)
    monkeypatch.setattr(sys, "argv", ["factory_reset.py"])

    rc = _fr.main()
    out = capsys.readouterr().out
    assert rc == 0
    assert "DRY RUN" in out
    assert "Would delete" in out
    assert "Would preserve" in out
    assert (faces / "faces.db").exists()  # untouched


def test_main_live_pipeline_refuses_returns_one(tmp_path, monkeypatch, capsys):
    """Lines 120-129 — live pipeline (fresh state.json) + no --force -> exit 1
    with an actionable stderr message."""
    faces = _redirect_fr_paths(monkeypatch, tmp_path)
    (faces / "state.json").write_text(
        json.dumps({"updated_at": time.time()}), encoding="utf-8"
    )
    monkeypatch.setattr(sys, "argv", ["factory_reset.py", "--confirm"])

    rc = _fr.main()
    err = capsys.readouterr().err
    assert rc == 1
    assert "Pipeline appears to be running" in err
    assert "--force" in err


def test_main_confirm_success_returns_zero(tmp_path, monkeypatch, capsys):
    """Happy wipe path (line 148-150 + 165) — --confirm --force with wipe_all
    mocked to a no-op returns 0. wipe_all is NEVER the real one (production
    faces/ must never be touched by the suite)."""
    _redirect_fr_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(_fr, "wipe_all", lambda: None)
    monkeypatch.setattr(sys, "argv", ["factory_reset.py", "--confirm", "--force"])

    rc = _fr.main()
    out = capsys.readouterr().out
    assert rc == 0
    assert "CONFIRMED" in out


def test_main_token_unlink_failure_returns_three(tmp_path, monkeypatch, capsys):
    """Lines 159-161 — with --include-dashboard-token, a token unlink that
    raises is caught, prints a WARN to stderr, and returns 3.

    We provoke a real failure (no pathlib monkeypatching): make
    `.dashboard_token` a DIRECTORY so `p.unlink(missing_ok=True)` raises
    (PermissionError on Windows / IsADirectoryError on POSIX — both Exception).
    wipe_all is mocked to a no-op so nothing real is deleted."""
    faces = _redirect_fr_paths(monkeypatch, tmp_path)
    (faces / ".dashboard_token").mkdir()  # a dir, not a file -> unlink fails
    monkeypatch.setattr(_fr, "wipe_all", lambda: None)
    monkeypatch.setattr(sys, "argv", [
        "factory_reset.py", "--confirm", "--include-dashboard-token", "--force",
    ])

    rc = _fr.main()
    err = capsys.readouterr().err
    assert rc == 3
    assert "could not delete" in err
    assert ".dashboard_token" in err


def test_main_wipe_all_raises_returns_two(tmp_path, monkeypatch, capsys):
    """Lines 162-164 — when wipe_all() itself raises, the outer except prints
    an ERROR to stderr and returns 2."""
    _redirect_fr_paths(monkeypatch, tmp_path)

    def _boom():
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(_fr, "wipe_all", _boom)
    monkeypatch.setattr(sys, "argv", ["factory_reset.py", "--confirm", "--force"])

    rc = _fr.main()
    err = capsys.readouterr().err
    assert rc == 2
    assert "wipe_all() raised" in err
    assert "disk on fire" in err


# ───────────────────────────────────────────────────────────────────────
# Module bootstrap guard (line 50) — kept LAST because it reloads the module.
# ───────────────────────────────────────────────────────────────────────


def test_repo_root_bootstrap_inserts_when_missing(monkeypatch):
    """Line 50 — the sys.path bootstrap body (`sys.path.insert(0, repo_root)`)
    runs only when the repo root is NOT already on sys.path (the real
    script-mode `python tools/factory_reset.py` invocation). In the pytest
    harness the repo root is already present, so line 50 is normally skipped.
    Reload the module under a sys.path that lacks the repo root so the insert
    executes and is measured.

    `importlib.reload` reuses the module's cached spec (loader still points at
    tools/factory_reset.py), and `from core.db import ...` resolves from
    sys.modules — so removing the repo root can't break the reload."""
    repo_root = str(_fr._REPO_ROOT)
    filtered = [p for p in sys.path if p != repo_root]
    monkeypatch.setattr(sys, "path", filtered)  # auto-restored at teardown

    importlib.reload(_fr)

    assert sys.path[0] == repo_root, (
        "reload with repo root absent must run the bootstrap insert (line 50)"
    )
    # sanity: the reloaded module still exposes its public surface
    assert callable(_fr.main)
    assert callable(_fr._is_pipeline_live)
