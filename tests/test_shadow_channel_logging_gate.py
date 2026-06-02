"""Latency D6 (Canary #2) — shadow-channel divergence prints gated behind a flag.

The 3 Phase-2 shadow diagnostics (VisionChannel-Shadow / VoiceChannel-Shadow /
Reconciler-Shadow) flooded the canary log every ~5s. Their COMPARISONS still run
(rollout-validation data); only their per-turn PRINTs are gated behind
SHADOW_CHANNEL_LOGGING_ENABLED (default False for canary cleanliness).

Spec: tests/pipeline_latency_fix_spec.md §2 D6 + §3 Layer 1.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _joinedstr_text(node: ast.AST) -> str:
    """Concatenate the literal string parts of an f-string / str constant."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(
            v.value for v in node.values
            if isinstance(v, ast.Constant) and isinstance(v.value, str)
        )
    return ""


def _build_parents(tree: ast.AST) -> dict:
    parents = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[id(child)] = parent
    return parents


def _gated_by_flag(node: ast.AST, parents: dict) -> bool:
    """True iff `node` is nested under an `if` whose test names SHADOW_CHANNEL_LOGGING_ENABLED."""
    cur = parents.get(id(node))
    while cur is not None:
        if isinstance(cur, ast.If):
            for t in ast.walk(cur.test):
                if isinstance(t, ast.Name) and t.id == "SHADOW_CHANNEL_LOGGING_ENABLED":
                    return True
        cur = parents.get(id(cur))
    return False


def test_d6_flag_exists_default_false():
    """core/config.py declares SHADOW_CHANNEL_LOGGING_ENABLED defaulting to False."""
    cfg = (REPO_ROOT / "core" / "config.py").read_text(encoding="utf-8")
    assert re.search(r"SHADOW_CHANNEL_LOGGING_ENABLED\s*=\s*False", cfg), (
        "SHADOW_CHANNEL_LOGGING_ENABLED must default to False (canary log cleanliness)"
    )


def test_d6_three_shadow_prints_gated_by_flag():
    """Each of the 3 shadow divergence prints is nested under an `if` whose test
    references SHADOW_CHANNEL_LOGGING_ENABLED (AST control-flow, not proximity)."""
    src = (REPO_ROOT / "pipeline.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    parents = _build_parents(tree)

    shadow_prints = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "print"
            and node.args
        ):
            text = _joinedstr_text(node.args[0])
            if "-Shadow]" in text and "divergence" in text:
                shadow_prints.append((getattr(node, "lineno", -1), text[:40]))
                assert _gated_by_flag(node, parents), (
                    f"shadow divergence print at line {node.lineno} is NOT gated by an "
                    "`if ... SHADOW_CHANNEL_LOGGING_ENABLED` block"
                )
    assert len(shadow_prints) >= 3, (
        f"expected >=3 shadow divergence prints (Vision/Voice/Reconciler), "
        f"found {len(shadow_prints)}: {shadow_prints}"
    )


def test_d6_comparisons_not_deleted():
    """The shadow COMPARISONS must remain (only the prints are gated, not the logic)."""
    src = (REPO_ROOT / "pipeline.py").read_text(encoding="utf-8")
    # Vision: the visible-set comparison; Voice: the identify_speaker shadow call;
    # Reconciler: the reconcile() shadow dispatch — all must still be present.
    assert "_prod_visible != _new_visible" in src, "vision shadow comparison must remain"
    assert "_vc_pid_diff or _vc_conf_diff" in src, "voice shadow comparison must remain"
    assert "_rule_fired not in _expected" in src, "reconciler shadow divergence-check must remain"
