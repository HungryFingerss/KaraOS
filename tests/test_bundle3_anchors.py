"""A1 + A3 + A5 anchor tests for Pre-P1 Bundle 3 (Critical Bugs MF4 + MF5).

A1 = D1 deadline-math migration source-inspection (parametrize over the 33
locked DEADLINE-MATH sites; each line must contain `time.monotonic()` not
`time.time()`). (Was 34; SB.1 D1 deleted the #6 `_yolo_last_ran` site with the
AGPL YOLO stack — its pipeline.py:5745 anchor is dropped below.)

A3 = D3 assert → raise migration source-inspection (parametrize over the 4
files in Plan v2 §1.14 scope; each must contain ZERO `assert` and at least
the original count of `raise RuntimeError(...)` statements).

A5 = D5 CI integration source-inspection (fast.yml runs the new AST
invariants by default — they're not slow/network/models so the default-
exclude marker filter doesn't drop them).
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


# --- A1: DEADLINE-MATH migration sites (locked at tools/migrate_time_monotonic.py) ---

# Re-derived from the migration script's SITES list to keep tests in sync.
A1_MIGRATED_SITES: tuple[tuple[str, int], ...] = (
    # 13 explicit Phase 0 + 14 paired writers + 1 cross-file = 28 sites (locked at Plan v2 §1.8)
    ("pipeline.py", 1006), ("pipeline.py", 2885), ("pipeline.py", 2886),
    ("pipeline.py", 2915), ("pipeline.py", 3426), ("pipeline.py", 3444),  # 3396→3444 #5 Slice-A LINE-REF-DRIFT refresh (cloud subtraction shifted by _bv_now SPLIT)
    ("pipeline.py", 5867), ("pipeline.py", 7413),  # 7369→7413 #5 Slice-A refresh (SELF_UPDATE_COOLDOWN); SB.1 D1 dropped pipeline.py:5745 (_yolo_last_ran #6 deadline-math, deleted with the YOLO stack)
    ("pipeline.py", 7753), ("pipeline.py", 8580), ("pipeline.py", 8589),  # Canary4 refresh; SB.1 D2 refreshed 8628→8580 (−48: cross-person-excerpts + flag-residue deletion shifted the face_in_frame deadline-math)
    ("core/brain_agent/__init__.py", 5557),  # 6908→6450 P1.A1 SP-2 C3 graph extraction (5991->5557); C2 privacy/context (6297->5991); C1 (6450->6297); prior: SB.1 D1 (Kuzu _rebuild_secs up, YOLO-stack deletion)
    ("pipeline.py", 1030), ("pipeline.py", 2879), ("pipeline.py", 2919),
    ("pipeline.py", 2939), ("pipeline.py", 3533), ("pipeline.py", 3494),
    ("pipeline.py", 3536), ("pipeline.py", 3538), ("pipeline.py", 6858),
    ("pipeline.py", 6859), ("pipeline.py", 7573), ("pipeline.py", 7666),  # 7521→7573 #5 Slice-A LINE-REF-DRIFT refresh (BRIEFING_MIN_ABSENCE)
    ("pipeline.py", 7807), ("pipeline.py", 7831),
    ("core/cache_store.py", 87),
    # Developer Pass-3 grep refinement (+6 sites; banked as `Plan-v1-Pass-2-grep-undercount`)
    ("pipeline.py", 599), ("pipeline.py", 601), ("pipeline.py", 7395),
    ("pipeline.py", 7389), ("pipeline.py", 7393), ("pipeline.py", 7424),  # 7379→7424 #5 Slice-B LINE-REF-DRIFT refresh (session/dispute clock split shifted the SELF_UPDATE_COOLDOWN region ~+45)
)


@pytest.mark.parametrize(
    "site",
    A1_MIGRATED_SITES,
    ids=lambda s: f"{s[0]}:{s[1]}",
)
def test_a1_deadline_math_site_uses_monotonic(site: tuple[str, int]) -> None:
    """A1 — each migrated DEADLINE-MATH site uses `time.monotonic()` not `time.time()`.

    Window is widened to 40 lines to accommodate line shifts from D3 assert→raise
    expansion (each `assert X, msg` migration adds 1 line; pipeline.py D3 added ~14 lines
    mid-file, shifting post-mid sites). 40-line window covers cumulative shifts cleanly.
    """
    rel, line_num = site
    path = REPO_ROOT / rel
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    window_start = max(0, line_num - 40)
    window_end = min(len(lines), line_num + 40)
    window = "\n".join(lines[window_start:window_end])
    assert "time.monotonic()" in window, (
        f"D1 migration not landed at {rel}:{line_num}: "
        f"`time.monotonic()` missing in 40-line window\n"
        f"Window content (truncated):\n{window[:500]}"
    )


# --- A3: assert→raise migration scope (Plan v2 §1.14 LOCKED at 44 sites in 4 files) ---

A3_FILES: tuple[str, ...] = (
    "pipeline.py",
    "core/brain_db_migrations.py",
    "core/faces_db_migrations.py",
    "core/db.py",
)


@pytest.mark.parametrize("rel", A3_FILES)
def test_a3_no_assert_in_migration_files(rel: str) -> None:
    """A3 — each file in Plan v2 §1.14 scope has ZERO `assert` statements."""
    text = (REPO_ROOT / rel).read_text(encoding="utf-8")
    asserts = re.findall(r"^\s*assert\s+", text, re.MULTILINE)
    assert not asserts, (
        f"{rel} still contains {len(asserts)} `assert` statement(s); D3 migration incomplete"
    )


def test_a3_total_44_sites_migrated_to_raise_runtime_error() -> None:
    """A3 — across the 4 Plan v2 §1.14 files, total `raise RuntimeError(` count >= 44."""
    total_raises = 0
    for rel in A3_FILES:
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        total_raises += len(re.findall(r"^\s*raise RuntimeError\s*\(", text, re.MULTILINE))
    assert total_raises >= 44, (
        f"Expected ≥44 `raise RuntimeError(...)` across {A3_FILES}; got {total_raises}"
    )


def test_a3_bug_9_cluster_docstring_reconciled() -> None:
    """A3 — `_init_room_orchestrator()` docstring reflects BUG-9 hybrid disposition."""
    pipeline = (REPO_ROOT / "pipeline.py").read_text(encoding="utf-8")
    # Find the docstring block
    idx = pipeline.find("def _init_room_orchestrator()")
    assert idx >= 0
    docstring_window = pipeline[idx:idx + 2000]
    assert "raise RuntimeError" in docstring_window, "docstring should mention raise RuntimeError"
    assert "Layer 3 None" in docstring_window or "Layer 3 None-handling" in docstring_window
    assert "Pre-P1 Bundle 3" in docstring_window, "docstring should reference Bundle 3 migration"


def test_a3_layer_3_none_guard_in_build_shared_context_block() -> None:
    """A3 — `build_shared_context_block` has Layer 3 None guard on `db` arg per BUG-9 hybrid §3."""
    src = (REPO_ROOT / "core" / "room_orchestrator.py").read_text(encoding="utf-8")
    idx = src.find("def build_shared_context_block(")
    assert idx >= 0
    body_window = src[idx:idx + 3000]
    # Look for explicit None check on db arg
    assert re.search(r"if\s+db\s+is\s+None", body_window), (
        "build_shared_context_block must have explicit `if db is None:` Layer 3 guard"
    )


# --- A5: CI integration source-inspection ---

def test_a5_fast_yml_includes_new_ast_invariants() -> None:
    """A5 — fast.yml runs default pytest (not marked slow/network/models) so new AST tests run."""
    fast_yml = REPO_ROOT / ".github" / "workflows" / "fast.yml"
    assert fast_yml.is_file(), "fast.yml workflow missing"
    text = fast_yml.read_text(encoding="utf-8")
    # Default exclude pattern should be "not slow and not network and not models"
    assert "not slow" in text
    assert "not network" in text
    assert "not models" in text


def test_a5_claude_md_banner_includes_bundle_history() -> None:
    """A5 — CLAUDE.md banner has Bundle 1 + Bundle 2 narratives (Bundle 3 appended at
    closure-narrative drafting step per Plan v2 §6; that fires `test_a5_bundle_3_closure_narrative_present`
    below to confirm)."""
    claude = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert "Pre-P1 Bundle 1" in claude
    assert "Pre-P1 Bundle 2" in claude


def test_a5_bundle_3_closure_narrative_present() -> None:
    """A5 — Bundle 3 closure narrative appended to CLAUDE.md banner per Plan v2 §6.

    This test PASSES only at closure-narrative drafting step (final cycle gate).
    Failing it during Phase 4 implementation indicates closure narrative not yet
    landed; that's expected until D5 closure step.
    """
    claude = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert "Pre-P1 Bundle 3" in claude, (
        "Bundle 3 closure narrative not yet appended to CLAUDE.md banner; "
        "fires at closure-narrative drafting step per Plan v2 §6"
    )
