"""tests/test_p0_s9_helper_scripts_transactions.py — P0.S9 source-inspection anchors.

Plan v1 §3 LOCK at 7 logical anchors across 4 D-decisions:
- D1 (consolidate by redirect): 2 anchors — no `def repair_gallery` in core/audit.py
  + audit_person.py calls `db.prune_outlier_embeddings` (and no `repair_gallery(`).
- D2 (explicit transaction wrap): 2 anchors — `delete_person_data` + `prune_shadows_mentioning`
  each contain `with self.transaction():` and no trailing `self._conn.commit()`.
- D3 (inverse-check coverage extension): 1 anchor — test file contains `_scan_paths`
  helper + `_SCAN_EXCLUDE` constant + scan iterates `core/*.py` (top-level glob).
- D4 (dry-run + confirm + default-deny gate): 2 anchors — `delete_person.py` has
  `--dry-run` + `--confirm` argparse flags; default-deny gate logic present.

Source-inspection by design — DLL-safe, no pipeline import, runs in CI on every PR.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import ast
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parent.parent
_AUDIT_PY = _REPO_ROOT / "core" / "audit.py"
_AUDIT_PERSON_PY = _REPO_ROOT / "audit_person.py"
_BRAIN_AGENT_PY = _REPO_ROOT / "core" / "brain_agent.py"
_INVERSE_TEST_PY = _REPO_ROOT / "tests" / "test_faiss_atomicity_invariants.py"
_DELETE_PERSON_PY = _REPO_ROOT / "delete_person.py"


def _read(p: Path) -> str:
    assert p.exists(), f"P0.S9 anchor expects {p} to exist"
    return p.read_text(encoding="utf-8")


def _find_method_in_class(tree: ast.AST, class_name: str, method_name: str) -> ast.FunctionDef | None:
    """Find a method by name within a specific class definition."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == method_name:
                    return child
    return None


# ───────────────────────────────────────────────────────────────────────
# D1 — Consolidate by redirect (2 anchors)
# ───────────────────────────────────────────────────────────────────────


def test_p0_s9_d1_anchor_1_repair_gallery_deleted_from_core_audit():
    """D1 Anchor 1: `core/audit.py` contains NO `def repair_gallery`.

    The local `repair_gallery` duplicate (P0.5 inverse-check violation:
    missing `_index_lock`, no `transaction()`, no `_mark_faiss_dirty()`
    sentinel) was deleted entirely at P0.S9 D1 consolidation. The
    P0.5-correct path is `FaceDB.prune_outlier_embeddings(person_id)`.
    """
    src = _read(_AUDIT_PY)
    assert "def repair_gallery" not in src, (
        "P0.S9 D1: `def repair_gallery` resurrected in core/audit.py. "
        "The local duplicate violates P0.5 paired-write pattern. "
        "Use `FaceDB.prune_outlier_embeddings(person_id)` instead — "
        "that is the P0.5-correct paired-write site."
    )


def test_p0_s9_d1_anchor_2_audit_person_redirects_to_db_prune():
    """D1 Anchor 2: `audit_person.py` calls `db.prune_outlier_embeddings(person_id)`
    AND does NOT contain `repair_gallery(` (the deleted function name).
    """
    src = _read(_AUDIT_PERSON_PY)
    assert "db.prune_outlier_embeddings(person_id)" in src, (
        "P0.S9 D1: `audit_person.py` must call `db.prune_outlier_embeddings(person_id)` "
        "for the --repair flag (P0.5-correct paired-write path)."
    )
    assert "repair_gallery(" not in src, (
        "P0.S9 D1: `audit_person.py` still references the deleted `repair_gallery` function. "
        "All calls must go through `db.prune_outlier_embeddings(person_id)` instead."
    )


# ───────────────────────────────────────────────────────────────────────
# D2 — Explicit transaction() wraps (2 anchors)
# ───────────────────────────────────────────────────────────────────────


def test_p0_s9_d2_anchor_1_delete_person_data_uses_transaction_wrap():
    """D2 Anchor 1: `BrainDB.delete_person_data` body contains
    `with self.transaction():` AND does NOT contain `self._conn.commit()`
    (trailing implicit commit removed; transaction context manager owns the commit).
    """
    src = _read(_BRAIN_AGENT_PY)
    tree = ast.parse(src)
    method = _find_method_in_class(tree, "BrainDB", "delete_person_data")
    assert method is not None, "BrainDB.delete_person_data method must exist"
    body_src = ast.unparse(method)
    assert "with self.transaction():" in body_src, (
        "P0.S9 D2: `BrainDB.delete_person_data` MUST wrap DELETE ops in "
        "`with self.transaction():` for explicit BEGIN IMMEDIATE / COMMIT contract. "
        "Implicit single-commit pattern was the P0.S9 pre-fix shape."
    )
    assert "self._conn.commit()" not in body_src, (
        "P0.S9 D2: `BrainDB.delete_person_data` has trailing `self._conn.commit()` — "
        "the transaction context manager owns commit; trailing commit is redundant + "
        "would commit a SECOND time outside the transaction scope."
    )


def test_p0_s9_d2_anchor_2_prune_shadows_uses_transaction_wrap():
    """D2 Anchor 2: `BrainDB.prune_shadows_mentioning` body contains
    `with self.transaction():` AND does NOT contain `self._conn.commit()`.
    """
    src = _read(_BRAIN_AGENT_PY)
    tree = ast.parse(src)
    method = _find_method_in_class(tree, "BrainDB", "prune_shadows_mentioning")
    assert method is not None, "BrainDB.prune_shadows_mentioning method must exist"
    body_src = ast.unparse(method)
    assert "with self.transaction():" in body_src, (
        "P0.S9 D2: `BrainDB.prune_shadows_mentioning` MUST wrap shadow modifications "
        "in `with self.transaction():` for explicit BEGIN IMMEDIATE / COMMIT contract."
    )
    assert "self._conn.commit()" not in body_src, (
        "P0.S9 D2: `BrainDB.prune_shadows_mentioning` has trailing `self._conn.commit()` — "
        "the transaction context manager owns commit; trailing commit is redundant."
    )


# ───────────────────────────────────────────────────────────────────────
# D3 — P0.5 inverse-check scan surface extension (1 anchor)
# ───────────────────────────────────────────────────────────────────────


def test_p0_s9_d3_anchor_1_inverse_check_scans_core_glob():
    """D3 Anchor 1: P0.5 inverse-check test file contains `_scan_paths` helper
    AND `_SCAN_EXCLUDE` constant AND scan iterates `core/*.py` (top-level glob,
    NOT recursive `**/*.py`).
    """
    src = _read(_INVERSE_TEST_PY)
    assert "_scan_paths" in src, (
        "P0.S9 D3: `tests/test_faiss_atomicity_invariants.py` must define a "
        "`_scan_paths` helper to widen the inverse-check scan from core/db.py "
        "only to core/*.py (top-level)."
    )
    assert "_SCAN_EXCLUDE" in src, (
        "P0.S9 D3: `tests/test_faiss_atomicity_invariants.py` must define a "
        "`_SCAN_EXCLUDE` frozenset listing vendored subdirs (core/_minifasnet, "
        "core/event_log) that should NOT be scanned."
    )
    # Top-level glob, NOT recursive. Reject `**/*.py` shape; require `*.py` shape.
    # Acceptable glob patterns: core_dir.glob("*.py") or Path("core").glob("*.py")
    assert ".glob(\"*.py\")" in src or ".glob('*.py')" in src, (
        "P0.S9 D3: `_scan_paths` must use top-level glob `*.py` (NOT recursive `**/*.py`). "
        "Vendored subdirs `core/_minifasnet/` + `core/event_log/` would be scanned "
        "by recursive glob, polluting the inverse-check signal."
    )
    assert ".glob(\"**/*.py\")" not in src and ".glob('**/*.py')" not in src, (
        "P0.S9 D3: `_scan_paths` uses recursive `**/*.py` glob — would scan vendored "
        "subdirs that should be excluded. Use top-level `*.py` glob instead."
    )


# ───────────────────────────────────────────────────────────────────────
# D4 — delete_person.py safety flags (2 anchors)
# ───────────────────────────────────────────────────────────────────────


def test_p0_s9_d4_anchor_1_delete_person_argparse_has_safety_flags():
    """D4 Anchor 1: `delete_person.py` argparse has `--dry-run` flag AND `--confirm` flag.

    The cross-DB destructive op (highest blast radius script in repo) requires
    explicit flag selection — operator MUST pick one before the script runs.
    """
    src = _read(_DELETE_PERSON_PY)
    assert '"--dry-run"' in src or "'--dry-run'" in src, (
        "P0.S9 D4: `delete_person.py` argparse MUST define `--dry-run` flag "
        "for safe preview path (read-only; no destructive call)."
    )
    assert '"--confirm"' in src or "'--confirm'" in src, (
        "P0.S9 D4: `delete_person.py` argparse MUST define `--confirm` flag "
        "for explicit destructive-op gate (default-deny safety contract)."
    )


def test_p0_s9_d4_anchor_2_delete_person_has_default_deny_gate():
    """D4 Anchor 2: `delete_person.py` has default-deny gate — `if not args.dry_run
    and not args.confirm: ... sys.exit(1)` pattern present.

    Without explicit flag selection (--dry-run OR --confirm), the script exits
    with a non-zero status BEFORE touching any DB. This prevents accidental
    `python delete_person.py --id X` from running the destructive path.
    """
    src = _read(_DELETE_PERSON_PY)
    # Look for the conjunction of "not args.dry_run" + "not args.confirm" in the same source.
    # Order is not load-bearing; the AND combinator is.
    assert "not args.dry_run" in src and "not args.confirm" in src, (
        "P0.S9 D4: `delete_person.py` must have default-deny gate combining "
        "`not args.dry_run` AND `not args.confirm` (without explicit flag → exit 1)."
    )
    assert "sys.exit(1)" in src, (
        "P0.S9 D4: default-deny gate must exit with non-zero status when both "
        "flags absent (current state: no `sys.exit(1)` found)."
    )
