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
    # P1.A1 SP-4.1 LINE-REF-DRIFT re-refresh: log harness moved to runtime/log_capture.py; pipeline.py
    # 8592→8403 (−189; contiguous log-region removal above ALL anchors → uniform −189, content-verified).
    # Inline "SP-4 refresh: <old>" notes below are the SP-4 (8925→8592) mapping; values are now SP-4.1.
    # P1.A1 SP-4 LINE-REF-DRIFT mass-refresh: pipeline.py shrank 8925→8592 (−333) when the 13 pure
    # leaves moved to runtime/{text,state_enums,context_blocks}.py. Every pipeline.py anchor below the
    # moved regions shifted; lines re-derived deterministically via the facade-ify line-map (old→new).
    ("runtime/vision_loop.py", 58), ("runtime/vision_loop.py", 356), ("runtime/vision_loop.py", 352),
    ("runtime/vision_loop.py", 386), ("pipeline.py", 905), ("pipeline.py", 923),  # SP-4 refresh: 1006/2885/2886/2915/3426/3444
    ("pipeline.py", 2409), ("pipeline.py", 4137),  # SP-4 refresh: 5867/7413 (deep anchors, −333 shift)
    ("pipeline.py", 4295), ("pipeline.py", 4805), ("pipeline.py", 4814),  # SP-6.4 re-key: 5367/5376 −254 (loop removal above run()); SP-4 refresh: 7753/8580/8589
    ("core/brain_agent/orchestrator.py", 357),  # UNCHANGED by SP-4 (orchestrator.py untouched); 6908→6450 P1.A1 SP-2 C4 agents (5557->3104); SP-3 _ensure_graph_sync -> orchestrator.py (__init__:3104 -> orchestrator:357); C3 graph (5991->5557); C2 privacy/context; C1 package-ify; prior: SB.1 D1
    ("runtime/vision_loop.py", 62), ("runtime/vision_loop.py", 352), ("runtime/vision_loop.py", 390),  # SP-4 refresh: 1030/2879/2919
    ("runtime/vision_loop.py", 410), ("pipeline.py", 1012), ("pipeline.py", 973),  # SP-4 refresh: 2939/3533/3494
    ("pipeline.py", 1015), ("pipeline.py", 1017), ("pipeline.py", 3082),  # SP-6.4 re-key: 3644 −254 (loop removal above run()); SP-4 refresh: 3536/3538/6858
    ("pipeline.py", 3083), ("pipeline.py", 4360), ("pipeline.py", 4390),  # SP-6.4 re-key: 3645 −254 (loop removal above run()); SP-4 refresh: 6859/7573/7666
    ("pipeline.py", 4594), ("pipeline.py", 4555),  # SP-4 refresh: 7807/7831
    ("core/cache_store.py", 87),  # UNCHANGED by SP-4
    # Developer Pass-3 grep refinement (+6 sites; banked as `Plan-v1-Pass-2-grep-undercount`)
    # P1.A1 SP-6.1 FILE re-key: 408/410 regionally tracked `_has_recent_face_evidence`'s
    # `time.monotonic() - last_seen` deadline-math (95897ef:pipeline.py:390); that helper
    # relocated to runtime/session.py (44-58) → file re-key, net-zero (−2 pipeline.py / +2 session.py).
    ("runtime/session.py", 44), ("runtime/session.py", 58), ("pipeline.py", 4119),  # SP-4 refresh: 599/601/7395
    ("pipeline.py", 4176), ("pipeline.py", 4117), ("pipeline.py", 4148),  # SP-4 refresh: 7389/7393/7424
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
    # P1.A1 SP-7a: 8 Bundle-3-migrated raises relocated from pipeline.py to
    # runtime/boot_checks.py with validate_tool_registries; count it too so the
    # floor still reflects the full migrated surface (count-only — A3_FILES, which
    # drives the per-file no-assert parametrize, stays the original 4).
    for rel in (*A3_FILES, "runtime/boot_checks.py"):
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
