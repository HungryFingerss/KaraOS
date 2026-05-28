"""P0.S11 — factory reset CLI + post-wipe summary tests.

7 anchors per Plan v1 §3 LOCK at exact mid 7 (NARROW band [5.95, 8.05]):

  A1 — D1.A1 source-inspection: tools/factory_reset.py exists with module
       docstring naming P0.S11 + canary date + Usage block.
  A2 — D1.A2 behavioral: --confirm-less invocation returns exit 0, prints
       "DRY RUN", lists targets, deletes nothing.
  A3 — D1.A3 behavioral: --confirm preserves token by default; --confirm
       --include-dashboard-token deletes both .dashboard_token and
       .dashboard_auth_url.
  A4 — D1.A4 behavioral: pipeline-liveness check refuses to run when
       state.json::updated_at is fresh (< 10s); proceeds when stale.
  A5 — D2 source-inspection: core/db.py::wipe_all contains _DELETED_PROBE_TARGETS
       + _PRESERVED_PROBE_TARGETS + Path.exists() probe + [Reset] Summary: line.
  A6 — D2 behavioral: wipe_all() against tmp_path produces summary line with
       correct deleted count + verbose enumeration; preserved files show kept.
  A7 — D3 source-inspection: tests/canary_week_2026-05-26.md references
       tools/factory_reset.py + the file actually exists post-D1.

Spec: tests/p0_s11_factory_reset_cli_plan_v1.md
"""
from __future__ import annotations

import json
import sqlite3
import sys
import time
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parent.parent
_TOOLS_DIR = _REPO_ROOT / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import factory_reset as _fr  # noqa: E402


# ───────────────────────────────────────────────────────────────────────
# A1 — source-inspection on tools/factory_reset.py
# ───────────────────────────────────────────────────────────────────────


def test_a1_factory_reset_cli_module_docstring_anchors_present():
    """D1.A1 — tools/factory_reset.py module-level docstring MUST contain
    `P0.S11` spec anchor + `2026-05-27` canary date + `Usage:` block.
    """
    script = _TOOLS_DIR / "factory_reset.py"
    assert script.is_file(), "tools/factory_reset.py must exist (D1.A1)"
    text = script.read_text(encoding="utf-8")
    assert "P0.S11" in text, "module docstring must reference P0.S11 spec"
    assert "2026-05-27" in text, "module docstring must reference canary date"
    assert "Usage:" in text, "module docstring must include Usage block"
    # Three flags documented
    assert "--confirm" in text, "must document --confirm flag"
    assert "--include-dashboard-token" in text, "must document --include-dashboard-token flag"
    assert "--force" in text, "must document --force flag"


# ───────────────────────────────────────────────────────────────────────
# Shared fixture — redirect all wipe paths to tmp_path
# ───────────────────────────────────────────────────────────────────────


def _redirect_paths_to_tmp(monkeypatch, tmp_path: Path) -> Path:
    """Point core.db + factory_reset path constants at tmp_path.

    Returns the faces_dir under tmp_path so tests can seed fixtures there.
    """
    from core import db as _db_mod

    faces_dir = tmp_path / "faces"
    faces_dir.mkdir(parents=True, exist_ok=True)

    # Redirect core.db paths (wipe_all reads these at call time)
    monkeypatch.setattr(_db_mod, "DB_PATH", faces_dir / "faces.db")
    monkeypatch.setattr(_db_mod, "FAISS_INDEX_PATH", faces_dir / "faiss.index")
    monkeypatch.setattr(_db_mod, "BRAIN_DB_PATH", faces_dir / "brain.db")
    monkeypatch.setattr(_db_mod, "GRAPH_DB_PATH", faces_dir / "brain_graph")
    monkeypatch.setattr(_db_mod, "FACES_DIR", faces_dir)
    monkeypatch.setattr(_db_mod, "ENROLL_REQUEST_FILE", faces_dir / "enroll_req.tmp")
    monkeypatch.setattr(_db_mod, "ENROLL_RESULT_FILE", faces_dir / "enroll_res.tmp")
    monkeypatch.setattr(_db_mod, "RESET_REQUEST_FILE", faces_dir / "reset_req.tmp")
    monkeypatch.setattr(_db_mod, "RESET_RESULT_FILE", faces_dir / "reset_res.tmp")

    # Redirect factory_reset CLI's `from core.db import` bound names
    monkeypatch.setattr(_fr, "DB_PATH", faces_dir / "faces.db")
    monkeypatch.setattr(_fr, "FAISS_INDEX_PATH", faces_dir / "faiss.index")
    monkeypatch.setattr(_fr, "BRAIN_DB_PATH", faces_dir / "brain.db")
    monkeypatch.setattr(_fr, "GRAPH_DB_PATH", faces_dir / "brain_graph")
    monkeypatch.setattr(_fr, "FACES_DIR", faces_dir)

    return faces_dir


# ───────────────────────────────────────────────────────────────────────
# A2 — behavioral dry-run mode
# ───────────────────────────────────────────────────────────────────────


def test_a2_cli_dry_run_default_lists_targets_deletes_nothing(tmp_path, monkeypatch, capsys):
    """D1.A2 — Invocation WITHOUT --confirm enters dry-run mode: exits 0,
    prints "DRY RUN", lists would-delete targets, and DELETES NOTHING.
    """
    faces_dir = _redirect_paths_to_tmp(monkeypatch, tmp_path)
    # Seed a fake faces.db artifact so dry-run lists it as "exists"
    (faces_dir / "faces.db").write_text("dummy", encoding="utf-8")
    (faces_dir / ".dashboard_token").write_text("T" * 43, encoding="utf-8")

    monkeypatch.setattr(sys, "argv", ["factory_reset.py"])
    rc = _fr.main()
    out = capsys.readouterr().out

    assert rc == 0, "dry-run must exit 0"
    assert "DRY RUN" in out, "must print DRY RUN marker"
    assert "Would delete" in out, "must enumerate would-delete targets"
    assert "Would preserve" in out, "must enumerate preserved targets"
    assert "--confirm" in out, "must instruct user to re-run with --confirm"

    # Critically: NO files deleted in dry-run
    assert (faces_dir / "faces.db").exists(), "dry-run MUST NOT delete files"
    assert (faces_dir / ".dashboard_token").exists(), "dry-run MUST NOT delete token"


# ───────────────────────────────────────────────────────────────────────
# A3 — behavioral --confirm preservation semantic
# ───────────────────────────────────────────────────────────────────────


def test_a3_confirm_preserves_dashboard_token_by_default(tmp_path, monkeypatch, capsys):
    """D1.A3 — --confirm WITHOUT --include-dashboard-token preserves both
    .dashboard_token and .dashboard_auth_url per P0.S2 invariant.
    """
    faces_dir = _redirect_paths_to_tmp(monkeypatch, tmp_path)
    token = "T" * 43
    (faces_dir / ".dashboard_token").write_text(token, encoding="utf-8")
    (faces_dir / ".dashboard_auth_url").write_text(
        f"http://127.0.0.1:3000/api/auth?token={token}", encoding="utf-8"
    )
    # Seed faces.db so wipe has something real to delete
    conn = sqlite3.connect(str(faces_dir / "faces.db"))
    conn.execute("CREATE TABLE marker (id INT)")
    conn.commit()
    conn.close()

    monkeypatch.setattr(sys, "argv", ["factory_reset.py", "--confirm", "--force"])
    rc = _fr.main()
    out = capsys.readouterr().out

    assert rc == 0, f"--confirm must exit 0 on success (got {rc})"
    assert "CONFIRMED" in out, "must announce confirmation"
    # P0.S2 preservation invariant
    assert (faces_dir / ".dashboard_token").exists(), (
        "P0.S2: .dashboard_token MUST survive default --confirm"
    )
    assert (faces_dir / ".dashboard_token").read_text(encoding="utf-8") == token
    assert (faces_dir / ".dashboard_auth_url").exists(), (
        "P0.S2: .dashboard_auth_url MUST survive default --confirm"
    )
    # faces.db actually deleted
    assert not (faces_dir / "faces.db").exists(), "wipe_all must delete faces.db"


def test_a3_include_dashboard_token_deletes_both_files(tmp_path, monkeypatch, capsys):
    """D1.A3 second branch — --confirm --include-dashboard-token deletes
    both .dashboard_token and .dashboard_auth_url (override P0.S2 default).
    """
    faces_dir = _redirect_paths_to_tmp(monkeypatch, tmp_path)
    (faces_dir / ".dashboard_token").write_text("T" * 43, encoding="utf-8")
    (faces_dir / ".dashboard_auth_url").write_text("http://localhost/", encoding="utf-8")

    monkeypatch.setattr(sys, "argv", [
        "factory_reset.py", "--confirm", "--include-dashboard-token", "--force",
    ])
    rc = _fr.main()
    out = capsys.readouterr().out

    assert rc == 0, f"--include-dashboard-token must exit 0 (got {rc})"
    assert "--include-dashboard-token" in out, "must announce token deletion mode"
    assert not (faces_dir / ".dashboard_token").exists(), (
        "--include-dashboard-token MUST delete .dashboard_token"
    )
    assert not (faces_dir / ".dashboard_auth_url").exists(), (
        "--include-dashboard-token MUST delete .dashboard_auth_url"
    )


# ───────────────────────────────────────────────────────────────────────
# A4 — behavioral pipeline-liveness check
# ───────────────────────────────────────────────────────────────────────


def test_a4_pipeline_live_refuses_without_force(tmp_path, monkeypatch, capsys):
    """D1.A4 — When state.json::updated_at is within last 10s, the CLI
    refuses to run and exits 1 with an actionable error to stderr.
    """
    faces_dir = _redirect_paths_to_tmp(monkeypatch, tmp_path)
    # Write a "live" state.json (updated_at = now)
    state_path = faces_dir / "state.json"
    state_path.write_text(json.dumps({"updated_at": time.time()}), encoding="utf-8")

    monkeypatch.setattr(sys, "argv", ["factory_reset.py", "--confirm"])
    rc = _fr.main()
    captured = capsys.readouterr()

    assert rc == 1, "live-pipeline refusal must exit 1"
    assert "Pipeline appears to be running" in captured.err, (
        "must print actionable error to stderr"
    )
    assert "--force" in captured.err, "error must mention --force override"


def test_a4_pipeline_stale_state_proceeds(tmp_path, monkeypatch, capsys):
    """D1.A4 — When state.json::updated_at is stale (> 10s ago), the CLI
    proceeds normally without --force.
    """
    faces_dir = _redirect_paths_to_tmp(monkeypatch, tmp_path)
    # Backdated state.json
    state_path = faces_dir / "state.json"
    state_path.write_text(
        json.dumps({"updated_at": time.time() - 30}), encoding="utf-8"
    )
    # Seed faces.db to give wipe something to do
    (faces_dir / "faces.db").write_text("dummy", encoding="utf-8")

    monkeypatch.setattr(sys, "argv", ["factory_reset.py", "--confirm"])
    rc = _fr.main()
    out = capsys.readouterr().out

    assert rc == 0, f"stale pipeline state must allow proceed (got {rc})"
    assert "CONFIRMED" in out, "must reach wipe phase"


# ───────────────────────────────────────────────────────────────────────
# A5 — source-inspection on core/db.py::wipe_all
# ───────────────────────────────────────────────────────────────────────


def test_a5_wipe_all_contains_post_wipe_summary_block():
    """D2 — core/db.py::wipe_all body MUST contain the post-wipe summary
    block introduced by P0.S11: _DELETED_PROBE_TARGETS + _PRESERVED_PROBE_TARGETS
    + Path.exists() probe + [Reset] Summary: line.

    A5 STRENGTHENED at Phase 5 regression (g) — substring check was prefix-
    collision-permissive (e.g. _DROPPED_DELETED_PROBE_TARGETS contained the
    target substring). Tightened to AST Assign with target Name("_DELETED_*")
    so a rename to a different identifier fires the test correctly. Same
    family-shape as P0.R8 A2 / P0.R10 A6 / P0.R12-R15 A3 strengthenings
    under `### Induction-surfaces-invariant-gaps` operational rule 3.
    """
    import ast as _ast
    db_src = (_REPO_ROOT / "core" / "db.py").read_text(encoding="utf-8")
    assert "def wipe_all(" in db_src, "wipe_all function must exist"
    # AST-precise: find wipe_all function body and scan for the exact
    # identifier assignments (NOT substring — defends against renames
    # like _DROPPED_DELETED_PROBE_TARGETS that would falsely pass).
    tree = _ast.parse(db_src)
    wipe_all_node = None
    for node in _ast.walk(tree):
        if isinstance(node, _ast.FunctionDef) and node.name == "wipe_all":
            wipe_all_node = node
            break
    assert wipe_all_node is not None, "wipe_all FunctionDef must exist"
    assigned_names: set[str] = set()
    for node in _ast.walk(wipe_all_node):
        if isinstance(node, _ast.Assign):
            for target in node.targets:
                if isinstance(target, _ast.Name):
                    assigned_names.add(target.id)
    assert "_DELETED_PROBE_TARGETS" in assigned_names, (
        "D2 summary block must define _DELETED_PROBE_TARGETS (exact Name)"
    )
    assert "_PRESERVED_PROBE_TARGETS" in assigned_names, (
        "D2 summary block must define _PRESERVED_PROBE_TARGETS (exact Name)"
    )
    # Substring assertions for non-identifier markers still OK
    assert "[Reset] Summary:" in db_src, "must print [Reset] Summary: line"
    assert "Path(path).exists()" in db_src, "summary must probe via Path.exists()"
    assert "P0.S11 D2" in db_src, "comment must reference spec anchor"


# ───────────────────────────────────────────────────────────────────────
# A6 — behavioral wipe_all summary output
# ───────────────────────────────────────────────────────────────────────


def test_a6_wipe_all_summary_reports_correct_deleted_count(tmp_path, monkeypatch, capsys):
    """D2 — wipe_all() against tmp_path with pre-seeded faces.db + brain.db
    + .dashboard_token shows correct deleted count and verbose enumeration.
    """
    from core import db as _db_mod

    faces_dir = _redirect_paths_to_tmp(monkeypatch, tmp_path)
    # Seed real files for both target classes
    conn = sqlite3.connect(str(faces_dir / "faces.db"))
    conn.execute("CREATE TABLE marker (id INT)")
    conn.commit()
    conn.close()
    conn = sqlite3.connect(str(faces_dir / "brain.db"))
    conn.execute("CREATE TABLE marker (id INT)")
    conn.commit()
    conn.close()
    # Preserved token (must show as "kept" in summary)
    (faces_dir / ".dashboard_token").write_text("T" * 43, encoding="utf-8")
    (faces_dir / ".dashboard_auth_url").write_text("http://localhost/", encoding="utf-8")

    _db_mod.wipe_all()
    out = capsys.readouterr().out

    # Summary line present
    assert "[Reset] Summary:" in out, "must print summary line"
    assert "deleted" in out, "summary must report deletion count"
    assert "P0.S2 invariant" in out, "summary must reference preservation invariant"

    # Verbose enumeration
    assert "[Reset] Deleted targets:" in out, "must enumerate deleted targets"
    assert "[Reset] Preserved targets" in out, "must enumerate preserved targets"

    # faces.db + brain.db should show as gone
    assert "gone" in out, "deleted files must show ✓ gone status"
    # .dashboard_token should show as kept
    assert "kept" in out, "preserved files must show ✓ kept status"
    assert ".dashboard_token" in out, ".dashboard_token must appear by name"


# ───────────────────────────────────────────────────────────────────────
# A7 — source-inspection on canary runbook reference
# ───────────────────────────────────────────────────────────────────────


def test_a7_canary_runbook_references_factory_reset_cli():
    """D3 verify-only — tests/canary_week_2026-05-26.md must reference
    `python tools/factory_reset.py` AND the script must exist post-D1.
    """
    canary = _REPO_ROOT / "tests" / "canary_week_2026-05-26.md"
    assert canary.is_file(), "canary runbook must exist"
    text = canary.read_text(encoding="utf-8")
    assert "python tools/factory_reset.py" in text, (
        "canary runbook must reference the CLI invocation"
    )
    # D3 contract: file actually exists post-D1
    cli_script = _TOOLS_DIR / "factory_reset.py"
    assert cli_script.is_file(), (
        "tools/factory_reset.py must exist (D1.A1) so the runbook reference resolves"
    )
