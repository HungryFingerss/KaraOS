"""tests/test_p0_s7_db.py — P0.S7.D-B Kuzu v3 schema bump.

Plan v2: ``tests/p0_s7_db_plan_v2.md``.

Closes the κ-ship-surfaced active leak (P0.S7.2 2026-05-19): the Kuzu
graph's RELATES_TO edges now carry a `privacy_level` STRING column;
cross-person `find_shared_entities` traversal filters at Cypher level
to public-tier only; `get_graph_context` mirrors the SQL
`_visibility_clause` semantic as defense-in-depth.

Test split per AST-forward-property-tests-are-the-workhorse discipline:
AST primary (catches schema/Cypher-text drift) + 1 slow behavioral
(catches Cypher syntax / live filter semantic).

Phase 1 tests (3) — schema + writers.
Phase 2 tests (2) — reader filters (D1 load-bearing + D3 defense-in-depth).
Phase 3 tests (3) — AST invariants (version constant + signature kwarg +
inverse-check for every `_create_edge` caller passing `privacy_level=`).
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import ast
import inspect
import re
import textwrap

import pytest

# P0.S7 D2 — module-level privacy_critical marker; all tests verify the
# Kuzu v3 privacy_level edge attribute + find_shared_entities filtering.
pytestmark = pytest.mark.privacy_critical


# ── Phase 1 tests — schema + writers ───────────────────────────────────────

def test_p0_s7_db_init_schema_declares_privacy_level_on_relates_to():
    """P0.S7.D-B Phase 1 test 1 — AST-forward-property.

    `GraphDB._init_schema` MUST declare `privacy_level STRING` in the
    RELATES_TO CREATE statement. Without this, the column doesn't
    exist at runtime and every subsequent write of a `privacy_level`
    value would fail with a Kuzu schema error.

    Schema-level structural anchor for the v3 bump.
    """
    from core.brain_agent import GraphDB

    src = inspect.getsource(GraphDB._init_schema)
    assert "RELATES_TO" in src, "method must define the RELATES_TO REL TABLE"
    assert "privacy_level STRING" in src, (
        "v3 schema bump missing — RELATES_TO MUST declare "
        "`privacy_level STRING` for cross-person Cypher filtering. "
        f"Got source:\n{src}"
    )


def test_p0_s7_db_create_edge_threads_privacy_level():
    """P0.S7.D-B Phase 1 test 2 — AST-forward-property.

    `GraphDB._create_edge` MUST:
      (i) accept `privacy_level: str` parameter with default 'personal'
          (D4 fail-closed) — matches PRIVACY_LEVEL_DEFAULT semantic.
      (ii) write the value to the new column in its Cypher CREATE.

    Catches the case where the schema declares the column but the
    writer forgets to populate it (silent NULL/empty leak).
    """
    from core.brain_agent import GraphDB

    src = inspect.getsource(GraphDB._create_edge)
    # (i) signature carries the new kwarg with default 'personal'.
    # Dedent — method source carries the class-body indent.
    tree = ast.parse(textwrap.dedent(src))
    fn = tree.body[0]
    assert isinstance(fn, ast.FunctionDef), "expected a FunctionDef"
    _param_names = [a.arg for a in fn.args.args] + [a.arg for a in fn.args.kwonlyargs]
    assert "privacy_level" in _param_names, (
        "_create_edge signature MUST accept `privacy_level` "
        f"kwarg; got params {_param_names}"
    )
    # Default 'personal' — D4 fail-closed. ast.unparse strips spaces
    # around `=`, so match on the space-normalized shape.
    _defaults_src = re.sub(r"\s+", " ", ast.unparse(fn.args))
    assert (
        "privacy_level: str='personal'" in _defaults_src
        or 'privacy_level: str="personal"' in _defaults_src
        or "privacy_level: str = 'personal'" in _defaults_src
        or 'privacy_level: str = "personal"' in _defaults_src
    ), (
        f"`privacy_level: str = 'personal'` default expected (D4 "
        f"fail-closed); got signature:\n{_defaults_src}"
    )
    # (ii) Cypher CREATE MUST write the column.
    assert "privacy_level: $privacy" in src, (
        "_create_edge Cypher CREATE MUST include `privacy_level: $privacy` "
        "alongside other edge properties (D2 edge-level placement)"
    )
    assert '"privacy": privacy_level' in src, (
        "_create_edge MUST bind the privacy_level value to the $privacy "
        "Cypher parameter"
    )


def test_p0_s7_db_store_fact_threads_extraction_privacy_level():
    """P0.S7.D-B Phase 1 test 3 — AST-forward-property.

    `GraphDB.store_fact` MUST pass `privacy_level=ext.privacy_level`
    to `_create_edge`. The Extraction dataclass carries privacy_level
    (set by S106 `_classify_privacy_level` at extraction time); without
    this thread-through, every store_fact-routed edge would default to
    'personal' regardless of the LLM-classified tier.

    Together with `rebuild_entity_from_knowledge` (test 6 covers the
    rebuild path), this closes the writer surface for v3.
    """
    from core.brain_agent import GraphDB

    src = inspect.getsource(GraphDB.store_fact)
    assert "_create_edge(" in src, "store_fact must call _create_edge"
    assert "privacy_level=ext.privacy_level" in src, (
        "store_fact MUST thread `privacy_level=ext.privacy_level` "
        "through to _create_edge. Without this, every fact-stored "
        "edge silently defaults to 'personal' regardless of the "
        "LLM-classified tier."
    )


# ── Phase 2 tests — reader filters (D1 load-bearing + D3 defense-in-depth) ──

def test_p0_s7_db_find_shared_entities_filters_to_public_only():
    """P0.S7.D-B Phase 2 test 4 — AST-forward-property (D1 LOAD-BEARING).

    `GraphDB.find_shared_entities` Cypher MUST include
    `r.privacy_level = 'public'` in its WHERE clause. This is the
    load-bearing privacy fix that closes the κ-ship-surfaced active
    leak (P0.S7.2 multi-person assistant-turn extraction writes
    personal-tier `received_*`/`witnessed_*` facts to brain.db; graph
    rebuild ingests them; without this filter, third-party visitors
    could surface them via cross-person matching).

    Cross-person owner-override does NOT apply to graph traversal —
    `find_shared_entities` is recipient-agnostic by design. Public-only
    is the correct semantic.
    """
    from core.brain_agent import GraphDB

    src = inspect.getsource(GraphDB.find_shared_entities)
    # Normalize whitespace so multi-line Cypher concatenation matches.
    _src_normalized = re.sub(r'"\s+"', "", src)
    _src_normalized = re.sub(r"\s+", " ", _src_normalized)
    assert "r.privacy_level = 'public'" in _src_normalized, (
        "find_shared_entities Cypher WHERE MUST include "
        "`r.privacy_level = 'public'` (D1 load-bearing privacy fix). "
        "Without this, personal/household/system_only edges leak via "
        f"cross-person traversal. Got source:\n{src}"
    )


@pytest.mark.slow
def test_p0_s7_db_find_shared_entities_skips_personal_tier_edges(tmp_path):
    """P0.S7.D-B Phase 2 test 5 — slow behavioral (real Kuzu).

    Plan v2 §4 worked example: a person's graph carries 3 edges all
    pointing to entity 'diabetes' with different attribute + privacy
    combinations. Only the public-tier edge survives the cross-person
    filter. Personal + system_only edges are filtered at Cypher level.

    This verifies the Cypher syntax actually works on a live Kuzu
    instance (catches dialect edge-cases) AND verifies the privacy
    semantic end-to-end.
    """
    import kuzu  # type: ignore[import-not-found]

    from core.brain_agent import GraphDB

    _path = tmp_path / "kuzu_db"
    gdb = GraphDB(str(_path))

    # Seed both persons' graphs with 3 edges all pointing to
    # 'diabetes' but with different attribute + privacy_level.
    # Plan v2 §4 schema-concept clarifier — same target entity name
    # can appear in multiple edges with different tiers per edge.
    _now = 1_000_000.0
    for person in ("Jagan", "Lexi"):
        gdb.upsert_entity(person, "person")
        gdb.upsert_entity("diabetes", "value")
        # Edge A — household tier, attribute 'discussed_topic'.
        gdb._create_edge(
            src=person, tgt="diabetes",
            attribute="discussed_topic", value="diabetes",
            confidence=0.9, is_temporal=False,
            valid_until=None, valid_at=_now,
            invalidated=False, source_turn_id=0, created_at=_now,
            privacy_level="household",
        )
        # Edge B — personal tier, attribute 'has_condition'.
        gdb._create_edge(
            src=person, tgt="diabetes",
            attribute="has_condition", value="diabetes",
            confidence=0.95, is_temporal=False,
            valid_until=None, valid_at=_now,
            invalidated=False, source_turn_id=0, created_at=_now,
            privacy_level="personal",
        )
        # Edge C — public tier, attribute 'knows_about'.
        gdb._create_edge(
            src=person, tgt="diabetes",
            attribute="knows_about", value="diabetes",
            confidence=0.8, is_temporal=False,
            valid_until=None, valid_at=_now,
            invalidated=False, source_turn_id=0, created_at=_now,
            privacy_level="public",
        )

    matches = gdb.find_shared_entities("Jagan", "Lexi", min_confidence=0.5)
    # Cross-person traversal MUST only surface the public-tier edge.
    # The personal + household edges MUST be filtered at Cypher level.
    _public_attrs = [m for m in matches if m["a_attribute"] == "knows_about"]
    _household_attrs = [m for m in matches if m["a_attribute"] == "discussed_topic"]
    _personal_attrs = [m for m in matches if m["a_attribute"] == "has_condition"]

    assert len(_public_attrs) > 0, (
        f"D1 LOAD-BEARING: public-tier 'knows_about' edge MUST "
        f"survive cross-person filter; got matches={matches}"
    )
    assert len(_household_attrs) == 0, (
        f"D1 LOAD-BEARING: household-tier 'discussed_topic' edge "
        f"MUST be filtered out of cross-person traversal; got "
        f"matches={matches}"
    )
    assert len(_personal_attrs) == 0, (
        f"D1 LOAD-BEARING: personal-tier 'has_condition' edge MUST "
        f"be filtered out of cross-person traversal (this is the "
        f"exact κ-ship leak vector); got matches={matches}"
    )


# ── Phase 3 tests — AST forward-property invariants ─────────────────────────

def test_p0_s7_db_graph_schema_version_is_three():
    """P0.S7.D-B Phase 3 test 8 — AST-forward-property.

    ``core.config.GRAPH_SCHEMA_VERSION`` MUST be 3. The schema-version
    trigger in ``_ensure_graph_sync`` fires drop+init+rebuild when the
    stored ledger version is less than this constant. If a future edit
    silently regresses the constant to 2, every fresh boot would skip
    the v3 schema upgrade and `find_shared_entities` would fail at
    Cypher level (missing privacy_level column).

    Also asserts the constant's defining line carries a P0.S7.D-B
    documentation reference so a code-archaeology reader sees WHY the
    bump happened, not just THAT it happened.
    """
    from core import config as _cfg

    assert _cfg.GRAPH_SCHEMA_VERSION == 3, (
        f"P0.S7.D-B bumped GRAPH_SCHEMA_VERSION 2→3; "
        f"got {_cfg.GRAPH_SCHEMA_VERSION}"
    )
    # Documentation cross-reference in the constant's defining file.
    import pathlib
    _config_src = pathlib.Path(_cfg.__file__).read_text(encoding="utf-8")
    # Find the GRAPH_SCHEMA_VERSION line (single-source-of-truth).
    _matches = [
        ln for ln in _config_src.splitlines()
        if ln.lstrip().startswith("GRAPH_SCHEMA_VERSION")
        and "=" in ln
    ]
    assert len(_matches) == 1, (
        f"expected exactly 1 GRAPH_SCHEMA_VERSION definition in config.py; "
        f"found {len(_matches)}: {_matches}"
    )
    _defining_line = _matches[0]
    assert "P0.S7.D-B" in _defining_line, (
        "GRAPH_SCHEMA_VERSION defining line MUST carry a P0.S7.D-B "
        f"reference so the v2→v3 bump rationale is anchored. Got: "
        f"{_defining_line!r}"
    )


def test_p0_s7_db_get_graph_context_signature_accepts_caller_pid():
    """P0.S7.D-B Phase 3 — AST-forward-property.

    `GraphDB.get_graph_context` signature MUST accept the `caller_pid`
    kwarg (and `best_friend_id` kwarg). Without them, the production
    caller at `BrainOrchestrator.get_context` (graph path) cannot
    thread the SQL `_visibility_clause`-equivalent semantic into
    Cypher. Catches the case where the signature regresses without
    a corresponding caller update.
    """
    from core.brain_agent import GraphDB

    src = textwrap.dedent(inspect.getsource(GraphDB.get_graph_context))
    tree = ast.parse(src)
    fn = tree.body[0]
    assert isinstance(fn, ast.FunctionDef), "expected a FunctionDef"

    _param_names = [a.arg for a in fn.args.args] + [a.arg for a in fn.args.kwonlyargs]
    assert "caller_pid" in _param_names, (
        f"get_graph_context signature MUST accept `caller_pid` kwarg "
        f"(P0.S7.D-B D3 defense-in-depth). Got params: {_param_names}"
    )
    assert "best_friend_id" in _param_names, (
        f"get_graph_context signature MUST accept `best_friend_id` kwarg "
        f"(D3 owner-override branch). Got params: {_param_names}"
    )


def test_p0_s7_db_every_create_edge_caller_passes_privacy_level():
    """P0.S7.D-B Phase 3 — AST-forward-property INVERSE-CHECK.

    Every call to `GraphDB._create_edge` in `core/brain_agent.py` MUST
    pass `privacy_level=` as an explicit keyword argument. The default
    (`'personal'`) is intentionally fail-closed for legacy + forgotten
    paths — but legitimate production writers MUST classify the tier
    explicitly so the v3 schema's privacy-aware traversal is honored.

    Inverse-check shape: scans every `Call` node in `brain_agent.py`
    whose function reference is `self._create_edge` or `_create_edge`;
    asserts every such call site carries `privacy_level=` kwarg.
    Catches new writer paths that forget the kwarg (silent 'personal'
    default would mask cross-person inference matches that should be
    public-tier).
    """
    import pathlib
    from core.brain_agent.memory import graph as _graph_mod

    # P1.A1 SP-2 C3: GraphDB + _create_edge (def + call sites) moved to
    # core/brain_agent/memory/graph.py; scan that module, not the package __init__.
    src = pathlib.Path(_graph_mod.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)

    _violations = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        # Match self._create_edge(...) and bare _create_edge(...).
        _func = node.func
        _name = None
        if isinstance(_func, ast.Attribute) and _func.attr == "_create_edge":
            _name = "_create_edge"
        elif isinstance(_func, ast.Name) and _func.id == "_create_edge":
            _name = "_create_edge"
        if _name is None:
            continue
        # SKIP the method-definition itself (the `def _create_edge`
        # node isn't a Call so this branch never matches it; left as
        # a defensive comment for future readers).
        _kwarg_names = [kw.arg for kw in node.keywords if kw.arg is not None]
        if "privacy_level" not in _kwarg_names:
            _violations.append(
                f"line {node.lineno}: _create_edge(...) call MISSING "
                f"`privacy_level=` kwarg. Got kwargs: {_kwarg_names}"
            )
    assert not _violations, (
        "P0.S7.D-B inverse-check failed: every `_create_edge(...)` call "
        "in core/brain_agent.py MUST pass `privacy_level=` kwarg "
        "explicitly. Without it, the default 'personal' tier applies "
        "silently — masking legitimate cross-person inference matches "
        "that should be public-tier.\n\nViolations:\n  "
        + "\n  ".join(_violations)
    )


