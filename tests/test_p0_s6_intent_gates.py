"""tests/test_p0_s6_intent_gates.py — P0.S6 tool-registry coverage invariants.

D1 — `INTENT_OPTIONAL_TOOLS: frozenset[str]` companion set in core/config.py.
D2 — Exhaustive intent-gate startup assertion in pipeline.py.
D3 — `_TOOL_FALLBACKS` coverage (2 new rows + assertion).
D4 — `INLINE_DISPATCHED_TOOLS: frozenset[str]` + `_TOOL_HANDLERS` assertion.
P3 — AST tripwire scanning core/config.py + pipeline.py for undocumented
     tool-registry dicts/sets (forward-property; catches future 5th-registry
     drift before it ships).

Spec: tests/p0_s6_intent_gates_audit.md + _plan_v1.md + _plan_v2.md.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import ast
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parent.parent


def _brain_tool_names() -> set[str]:
    from core.brain import TOOLS
    return {t["function"]["name"] for t in TOOLS}


# ═══════════════════════════════════════════════════════════════════════
# D1 — INTENT_OPTIONAL_TOOLS companion set
# ═══════════════════════════════════════════════════════════════════════


def test_d1_intent_optional_tools_exists_and_is_frozenset():
    """D1 — `INTENT_OPTIONAL_TOOLS` exists at module scope of core/config.py
    AND is a frozenset (NOT a set, list, dict — locking the immutable
    contract per Plan v1 §3.1 mitigation against future readers adding
    `(intent, arg_key)` tuples by analogy to TOOL_INTENT_MAP)."""
    from core.config import INTENT_OPTIONAL_TOOLS
    assert isinstance(INTENT_OPTIONAL_TOOLS, frozenset), (
        f"INTENT_OPTIONAL_TOOLS must be a frozenset (got {type(INTENT_OPTIONAL_TOOLS).__name__}). "
        f"Mutable types invite drift; frozenset locks the membership at module load."
    )


def test_d1_intent_optional_tools_content_locked():
    """D1 — INTENT_OPTIONAL_TOOLS membership locked at Plan v1 §1.D1: the
    3 search tools (search_web, search_memory, search_room_memory)."""
    from core.config import INTENT_OPTIONAL_TOOLS
    expected = frozenset({"search_web", "search_memory", "search_room_memory"})
    assert INTENT_OPTIONAL_TOOLS == expected, (
        f"INTENT_OPTIONAL_TOOLS content drifted from locked Plan v1 set. "
        f"Expected {sorted(expected)}; got {sorted(INTENT_OPTIONAL_TOOLS)}. "
        f"Adding a new tool here requires Plan v1 §1.D1 rationale block update."
    )


def test_d1_inline_dispatched_tools_exists_and_locked():
    """D4 (D1 sibling) — `INLINE_DISPATCHED_TOOLS` exists as frozenset at
    module scope of core/config.py with locked content per Plan v1 §1.D4."""
    from core.config import INLINE_DISPATCHED_TOOLS
    assert isinstance(INLINE_DISPATCHED_TOOLS, frozenset)
    expected = frozenset({"search_web", "search_room_memory"})
    assert INLINE_DISPATCHED_TOOLS == expected, (
        f"INLINE_DISPATCHED_TOOLS drifted: expected {sorted(expected)}; "
        f"got {sorted(INLINE_DISPATCHED_TOOLS)}. search_memory is INTENTIONALLY "
        f"absent (legacy dual-path with _TOOL_HANDLERS entry)."
    )


# ═══════════════════════════════════════════════════════════════════════
# D2 — Intent-gate registry exhaustive coverage
# ═══════════════════════════════════════════════════════════════════════


def test_d2_intent_registry_covers_every_brain_tool():
    """D2 — pytest-reachable mirror of the pipeline.run() startup assertion.
    Every tool in brain.TOOLS MUST appear in TOOL_INTENT_MAP OR
    INTENT_OPTIONAL_TOOLS."""
    from core.config import TOOL_INTENT_MAP, INTENT_OPTIONAL_TOOLS
    names = _brain_tool_names()
    known = set(TOOL_INTENT_MAP) | set(INTENT_OPTIONAL_TOOLS)
    missing = names - known
    orphans = known - names
    assert not missing, (
        f"Tools missing from TOOL_INTENT_MAP ∪ INTENT_OPTIONAL_TOOLS: "
        f"{sorted(missing)}"
    )
    assert not orphans, (
        f"Tools in registry but not in brain.TOOLS: {sorted(orphans)}"
    )


def test_d2_pipeline_runtime_assertion_source_present():
    """D2 — source-inspection that the runtime assertion block exists in
    pipeline.py with the expected shape (intent-known set construction +
    missing + orphan checks)."""
    src = (_REPO_ROOT / "pipeline.py").read_text(encoding="utf-8")
    assert "INTENT_OPTIONAL_TOOLS" in src
    assert "_intent_known" in src
    assert "_intent_missing" in src
    assert "_intent_orphans" in src
    assert "TOOL_INTENT_MAP ∪ INTENT_OPTIONAL_TOOLS" in src, (
        "D2 error message must name BOTH registries in the union "
        "(missing-gap shape) so the operator's next action is unambiguous"
    )


def test_d2_ordering_invariant_comment_present():
    """D2 — ORDERING INVARIANT comment block exists at the assertion site
    per Plan v1 §1.D2 P1 + P0.S3 §1.P3 shape precedent. Future
    maintainers grepping for ORDERING INVARIANT find this anchor."""
    src = (_REPO_ROOT / "pipeline.py").read_text(encoding="utf-8")
    # The D2 assertion's ORDERING INVARIANT comment must reference both
    # the privilege check (AFTER it) and env validation (AFTER it).
    idx_d2 = src.find("Intent-gate registry integrity check (P0.S6 D2)")
    assert idx_d2 != -1, "D2 assertion comment header missing"
    window = src[idx_d2:idx_d2 + 1500]
    assert "ORDERING INVARIANT" in window
    assert "AFTER the TOOL_PRIVILEGES" in window, (
        "D2 ORDERING INVARIANT must name the relative position vs "
        "TOOL_PRIVILEGES assertion (AFTER privilege check)"
    )
    assert "validate_required_env" in window, (
        "D2 ORDERING INVARIANT must reference env-validation (P0.S3 anchor) "
        "to lock the multi-spec ordering chain"
    )


def test_d2_assertion_fires_on_missing_tool(monkeypatch):
    """D2 — behavioral verification: extract the assertion logic, simulate
    a tool name in TOOLS without a TOOL_INTENT_MAP / INTENT_OPTIONAL_TOOLS
    entry → assertion fires with the missing-shape error body."""
    from core.config import TOOL_INTENT_MAP, INTENT_OPTIONAL_TOOLS
    # Simulate the assertion in isolation (the real call site at
    # pipeline.run() runs once at startup; replicating the logic here lets
    # us drive missing/orphan paths without a full pipeline launch).
    names = _brain_tool_names() | {"hypothetical_unregistered_tool"}
    known = set(TOOL_INTENT_MAP) | set(INTENT_OPTIONAL_TOOLS)
    missing = names - known
    assert missing == {"hypothetical_unregistered_tool"}, (
        f"D2 missing-detection logic broken: expected the injected name to "
        f"be the sole missing entry; got {missing!r}"
    )


def test_d2_assertion_fires_on_orphan_tool():
    """D2 — orphan-shape detection: a tool in the registry but missing
    from brain.TOOLS must surface as an orphan."""
    from core.config import TOOL_INTENT_MAP, INTENT_OPTIONAL_TOOLS
    names = _brain_tool_names() - {"shutdown"}  # simulate shutdown removed from TOOLS
    known = set(TOOL_INTENT_MAP) | set(INTENT_OPTIONAL_TOOLS)
    orphans = known - names
    assert "shutdown" in orphans, (
        "D2 orphan-detection logic broken: shutdown in registry but removed "
        "from simulated TOOLS should appear as orphan"
    )


# ═══════════════════════════════════════════════════════════════════════
# D3 — _TOOL_FALLBACKS coverage + assertion
# ═══════════════════════════════════════════════════════════════════════


def test_d3_fallback_rows_present_with_locked_content():
    """D3 — the 2 new fallback rows are present with locked content
    (per Plan v1 §1.D3 P2 + Plan v2 verbatim adjudication)."""
    import pipeline
    fb = pipeline._TOOL_FALLBACKS
    assert fb.get("report_identity_mismatch") == "Got it.", (
        f"D3 lock: report_identity_mismatch fallback must be 'Got it.' "
        f"(Session 28 Issue A acknowledge-then-stay-quiet precedent); "
        f"got {fb.get('report_identity_mismatch')!r}"
    )
    assert fb.get("search_room_memory") == "Let me think about that.", (
        f"D3 lock: search_room_memory fallback must mirror search_memory "
        f"(UX symmetry — same architectural shape); "
        f"got {fb.get('search_room_memory')!r}"
    )


def test_d3_fallback_registry_covers_every_brain_tool():
    """D3 — pytest-reachable mirror of the runtime assertion: every tool
    in brain.TOOLS must have a non-empty stripped fallback string."""
    import pipeline
    names = _brain_tool_names()
    missing = names - set(pipeline._TOOL_FALLBACKS)
    orphans = set(pipeline._TOOL_FALLBACKS) - names
    degenerate = {k for k, v in pipeline._TOOL_FALLBACKS.items() if not v.strip()}
    assert not missing, f"_TOOL_FALLBACKS missing entries for: {sorted(missing)}"
    assert not orphans, f"_TOOL_FALLBACKS has orphan entries: {sorted(orphans)}"
    assert not degenerate, (
        f"_TOOL_FALLBACKS has empty/whitespace-only values: {sorted(degenerate)}"
    )


def test_d3_pipeline_runtime_assertion_source_present():
    """D3 — source-inspection that the fallback runtime assertion block
    exists in pipeline.py with the expected shape (missing + orphan +
    degenerate-whitespace checks)."""
    src = (_REPO_ROOT / "pipeline.py").read_text(encoding="utf-8")
    assert "_fb_missing" in src
    assert "_fb_orphans" in src
    assert "_fb_degenerate" in src
    assert "non-empty after" in src, (
        "D3 degenerate-shape error must name str.strip() condition to "
        "make the operator-actionable distinction (missing vs whitespace-only)"
    )


def test_d3_ordering_invariant_comment_present():
    """D3 — ORDERING INVARIANT comment block at the assertion site,
    referencing the AFTER-D2 ordering position."""
    src = (_REPO_ROOT / "pipeline.py").read_text(encoding="utf-8")
    idx_d3 = src.find("Fallback registry integrity check (P0.S6 D3)")
    assert idx_d3 != -1, "D3 assertion comment header missing"
    window = src[idx_d3:idx_d3 + 1500]
    assert "ORDERING INVARIANT" in window
    assert "AFTER the intent-gate check" in window


def test_d3_fallback_degenerate_detection_logic():
    """D3 — verify the degenerate-string detection catches all 3 shapes
    (empty, whitespace-only, single newline) the assertion is meant to
    block (per Plan v1 §3.3 mitigation against degenerate prose)."""
    import pipeline
    # Local simulation of the runtime check logic
    degenerate_samples = ["", " ", "\n", "\t", "   "]
    for s in degenerate_samples:
        fake_fb = dict(pipeline._TOOL_FALLBACKS)
        fake_fb["fake_tool"] = s
        degenerate = {k for k, v in fake_fb.items() if not v.strip()}
        assert "fake_tool" in degenerate, (
            f"D3 degenerate-detection must catch {s!r}; got degenerate set {degenerate!r}"
        )


# ═══════════════════════════════════════════════════════════════════════
# D4 — _TOOL_HANDLERS + INLINE_DISPATCHED_TOOLS coverage
# ═══════════════════════════════════════════════════════════════════════


def test_d4_handler_registry_covers_every_brain_tool():
    """D4 — pytest-reachable mirror: every tool in brain.TOOLS must
    appear in _TOOL_HANDLERS OR INLINE_DISPATCHED_TOOLS."""
    import pipeline
    from core.config import INLINE_DISPATCHED_TOOLS
    names = _brain_tool_names()
    known = set(pipeline._TOOL_HANDLERS) | set(INLINE_DISPATCHED_TOOLS)
    missing = names - known
    orphans = set(pipeline._TOOL_HANDLERS) - names
    assert not missing, (
        f"Tools missing from _TOOL_HANDLERS ∪ INLINE_DISPATCHED_TOOLS: "
        f"{sorted(missing)}"
    )
    assert not orphans, (
        f"_TOOL_HANDLERS has orphan entries: {sorted(orphans)}"
    )


def test_d4_pipeline_runtime_assertion_source_present():
    """D4 — source-inspection that the handler runtime assertion block
    exists with expected shape."""
    src = (_REPO_ROOT / "pipeline.py").read_text(encoding="utf-8")
    assert "_handler_known" in src
    assert "_handler_missing" in src
    assert "_handler_orphans" in src
    assert "_TOOL_HANDLERS ∪ INLINE_DISPATCHED_TOOLS" in src


def test_d4_ordering_invariant_comment_present():
    """D4 — ORDERING INVARIANT comment block at the handler-assertion
    site, referencing the AFTER-D3 ordering position."""
    src = (_REPO_ROOT / "pipeline.py").read_text(encoding="utf-8")
    idx_d4 = src.find("Handler registry integrity check (P0.S6 D4)")
    assert idx_d4 != -1, "D4 assertion comment header missing"
    window = src[idx_d4:idx_d4 + 1500]
    assert "ORDERING INVARIANT" in window
    assert "AFTER the fallback check" in window


# ═══════════════════════════════════════════════════════════════════════
# P3 — AST tripwire for undocumented tool registries
# ═══════════════════════════════════════════════════════════════════════


# Allowlist of legitimate tool-name dicts/sets that are NOT coverage
# registries (per Plan v2 §1 adjudication option (b) — keep with rationale
# for grep-discoverability).
_REGISTRY_ALLOWLIST: dict[str, str] = {
    "_CONCURRENT_SAFE_TOOLS": (
        "concurrency-safe allowlist; intentionally narrow (1 tool today). "
        "Exclusion semantics (not inclusion) — adding a tool = "
        "'this tool is concurrency-safe.'"
    ),
    "HISTORY_OVERRIDE_TOOLS": (
        "history-rewrite allowlist; tools whose canonical-ack lands in "
        "conversation_log. Narrow-by-design (2 tools today)."
    ),
    "TOOL_TIMEOUT_OVERRIDES": (
        "per-tool timeout override map; default TOOL_TIMEOUT_SECS applies "
        "when absent. Override-only allowlist, not a coverage registry."
    ),
    "_KNOWN_TOOL_NAMES": (
        "regex pattern string (not a set/dict); AST type filter skips by "
        "annotation type; documented for grep-discoverability per Plan v2 "
        "§1 adjudication."
    ),
}

# The 4 coverage registries P0.S6 + P0.S6-prior locks. AST scan flags
# anything outside this set + the allowlist.
_LOCKED_COVERAGE_REGISTRIES: set[str] = {
    "TOOL_PRIVILEGES",
    "TOOL_INTENT_MAP",
    "_TOOL_FALLBACKS",
    "_TOOL_HANDLERS",
    # D1/D4 companion sets (not registries themselves, but exempt by name)
    "INTENT_OPTIONAL_TOOLS",
    "INLINE_DISPATCHED_TOOLS",
}


def _is_tool_name_container(node: ast.expr) -> bool:
    """Check whether the value expression is a dict/frozenset/set whose
    members overlap with brain.TOOLS names (at least one literal key).
    """
    names = _brain_tool_names()
    # Dict literal with string keys
    if isinstance(node, ast.Dict):
        for key in node.keys:
            if isinstance(key, ast.Constant) and isinstance(key.value, str) and key.value in names:
                return True
    # Set / frozenset literal with string elements
    elif isinstance(node, ast.Set):
        for elt in node.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str) and elt.value in names:
                return True
    # frozenset({...}) call
    elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "frozenset":
        if node.args and isinstance(node.args[0], ast.Set):
            for elt in node.args[0].elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str) and elt.value in names:
                    return True
    return False


def test_p3_no_undocumented_tool_registries():
    """P3 — AST tripwire: scan core/config.py + pipeline.py for module-level
    name bindings whose RHS is a dict/set/frozenset overlapping with
    brain.TOOLS names. Any binding NOT in the locked coverage registries
    OR the allowlist surfaces as a violation requiring rationale OR
    adoption as a new coverage registry."""
    scan_targets = ["core/config.py", "pipeline.py"]
    violations: list[tuple[str, str]] = []
    for target in scan_targets:
        src = (_REPO_ROOT / target).read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in tree.body:
            # Match module-level Assign / AnnAssign bindings
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                name = node.target.id
                value = node.value
            elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                name = node.targets[0].id
                value = node.value
            else:
                continue
            if value is None:
                continue
            if not _is_tool_name_container(value):
                continue
            if name in _LOCKED_COVERAGE_REGISTRIES:
                continue
            if name in _REGISTRY_ALLOWLIST:
                continue
            violations.append((target, name))
    assert not violations, (
        f"P0.S6 P3 AST tripwire FAILED — undocumented tool-name registries found:\n"
        + "\n".join(f"  {t}:{n}" for t, n in violations)
        + "\n\nFix: either (a) adopt as a new coverage registry with its own "
        "startup assertion + tests, OR (b) add to _REGISTRY_ALLOWLIST with "
        "a per-entry rationale explaining why it's exclusion-semantics, "
        "narrow-by-design, or override-only (not coverage)."
    )


def test_p3_allowlist_entries_have_rationale():
    """P3 inverse — every entry in `_REGISTRY_ALLOWLIST` must have a
    non-trivial rationale string. Prevents drift where someone silently
    appends a name to bypass the tripwire without explanation."""
    for name, rationale in _REGISTRY_ALLOWLIST.items():
        assert isinstance(rationale, str) and len(rationale.strip()) >= 20, (
            f"Allowlist entry {name!r} has insufficient rationale: {rationale!r}. "
            f"Rationale must be ≥20 chars naming WHY this name is not a coverage "
            f"registry (exclusion semantics, narrow-by-design, override-only, etc.)."
        )


# ═══════════════════════════════════════════════════════════════════════
# Cross-cutting — deliberate-regression confirmations (Phase 4 bundle)
# ═══════════════════════════════════════════════════════════════════════


def test_d1_d4_companion_sets_have_distinct_purposes():
    """Cross-cutting — INTENT_OPTIONAL_TOOLS and INLINE_DISPATCHED_TOOLS
    are NOT identical (they cover different aspects: classifier-gate
    exemption vs inline-dispatch shape). search_memory is INTENTIONALLY
    in INTENT_OPTIONAL_TOOLS (gate-exempt) but NOT in INLINE_DISPATCHED_TOOLS
    (has a _TOOL_HANDLERS entry from the legacy dual-path)."""
    from core.config import INTENT_OPTIONAL_TOOLS, INLINE_DISPATCHED_TOOLS
    # They differ — sanity-check the dual-purpose design
    assert INTENT_OPTIONAL_TOOLS != INLINE_DISPATCHED_TOOLS, (
        "INTENT_OPTIONAL_TOOLS and INLINE_DISPATCHED_TOOLS must differ — "
        "if they're identical, one is redundant. Plan v1 §1.D4 documents "
        "search_memory's intentional asymmetry."
    )
    # search_memory specifically: gate-exempt but NOT inline-only
    assert "search_memory" in INTENT_OPTIONAL_TOOLS
    assert "search_memory" not in INLINE_DISPATCHED_TOOLS
