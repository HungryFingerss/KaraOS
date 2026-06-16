"""SB.3 — agent-registry test battery (T1–T10).

Registry-driven agent construction (both sites — PI-1) + per-site presence
guards over the full invocation surface, behavior-neutral for companion.

Plan: karaos-org-discussions/solidify-base/SB3-1-plan-v1.md §7.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import ast
import asyncio
import pathlib
import sqlite3

import pytest

import core.config as config
import core.brain_agent.orchestrator as orch
from core.brain_agent.orchestrator import BrainOrchestrator, _ATTR, _topo_order
from core.profile_loader import ProfileError, _resolve
from profiles._registry import AGENT_BUNDLES, AGENT_REGISTRY

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
_ORCH_PY = REPO_ROOT / "core" / "brain_agent" / "orchestrator.py"
_REGISTRY_PY = REPO_ROOT / "profiles" / "_registry.py"
_CONFIG_PY = REPO_ROOT / "core" / "config.py"

# A synthetic "supermarket" profile: keeps ONLY watchdog (the kiosk's one
# DB-handle agent), drops every knowledge agent. Used by T2/T3 to exercise the
# mechanism — the shipped supermarket profile lands with the clone (§9).
SUPERMARKET = frozenset({"watchdog"})
_KNOWLEDGE = set(AGENT_REGISTRY) - {"watchdog"}


def _make_orch(tmp_path, monkeypatch, active) -> BrainOrchestrator:
    """Construct a BrainOrchestrator with the given ACTIVE_AGENTS + tmp DBs.
    Monkeypatches config.ACTIVE_AGENTS BEFORE construction (the orchestrator
    reads it by attribute at _build_agents time)."""
    monkeypatch.setattr(config, "ACTIVE_AGENTS", frozenset(active))
    # Seed the minimal faces.db schema the orchestrator's _faces_conn reads
    # (dream()'s first query is `SELECT id FROM persons`). Empty table → the
    # per-person decay loop is a no-op, so dream() reaches the schema-guard site
    # cheaply. The real FaceDB owns the full schema in production.
    _faces = tmp_path / "faces.db"
    _seed = sqlite3.connect(str(_faces))
    _seed.execute("CREATE TABLE IF NOT EXISTS persons (id TEXT PRIMARY KEY)")
    _seed.commit()
    _seed.close()
    return BrainOrchestrator(
        asyncio.Event(),
        brain_db_path=str(tmp_path / "brain.db"),
        graph_db_path=str(tmp_path / "graph"),
        faces_db_path=str(tmp_path / "faces.db"),
    )


# ────────────────────────────────────────────────────────────────────────────
# T1 — companion golden
# ────────────────────────────────────────────────────────────────────────────

def test_t1_companion_golden_construction(tmp_path, monkeypatch) -> None:
    """T1 — the companion orchestrator constructs all 15 agents with their exact
    classes + the embed→schema topo order. Drift fails CI (behavior-neutral)."""
    bo = _make_orch(tmp_path, monkeypatch, AGENT_BUNDLES["companion"])
    assert set(AGENT_REGISTRY) == set(_ATTR), "registry/_ATTR key drift"
    for name, spec in AGENT_REGISTRY.items():
        agent = getattr(bo, _ATTR[name])
        assert agent is not None, f"companion agent {name!r} should be constructed"
        assert type(agent).__name__ == spec["class"], (
            f"{name!r} built as {type(agent).__name__}, expected {spec['class']}"
        )
    order = _topo_order(AGENT_BUNDLES["companion"])
    assert order.index("embed") < order.index("schema")


# ────────────────────────────────────────────────────────────────────────────
# T2 — behavioral completeness on the RESET surface (Lock 1; PI-1 core)
# ────────────────────────────────────────────────────────────────────────────

async def test_t2_reset_surface_no_knowledge_invocation(tmp_path, monkeypatch) -> None:
    """T2 (Lock 1) — under a supermarket profile, the orchestrator invokes ZERO
    knowledge-agent methods across the factory-reset surface. A CLASS-level spy
    on SchemaNormAgent.maybe_run catches a regression that rebuilds schema at
    reset (the §2286-2289 bypass): post-reset the spy must NOT fire. The spy is
    on the class, so it observes the POST-reset object graph (the reset swaps in
    fresh objects via setattr — pre-reset instance spies wouldn't survive)."""
    from core.brain_agent.agents.schema import SchemaNormAgent

    calls: list[str] = []

    async def _spy_maybe_run(self):
        calls.append("maybe_run")

    monkeypatch.setattr(SchemaNormAgent, "maybe_run", _spy_maybe_run)

    bo = _make_orch(tmp_path, monkeypatch, SUPERMARKET)
    assert bo._schema_norm is None, "supermarket must not construct schema"

    bo.reopen_connections()                 # the PI-1 factory-reset surface
    assert bo._schema_norm is None, "reset must NOT reconstruct schema under supermarket"

    await bo.dream()                          # the dream schema site — guard must skip
    assert calls == [], (
        "schema.maybe_run was invoked post-reset under a supermarket profile — "
        "the reset-bypass leak (PI-1) is open"
    )


# ────────────────────────────────────────────────────────────────────────────
# T3 — reset-path construction (PI-1; primary net for Lock 1)
# ────────────────────────────────────────────────────────────────────────────

def test_t3_reset_drops_unregistered_db_agents(tmp_path, monkeypatch) -> None:
    """T3 — after a factory reset under a supermarket profile, the orchestrator
    holds NONE of {schema, routine, nudge} and DOES hold watchdog. Closes the
    :2286-2289 unconditional-rebuild bypass at construction."""
    bo = _make_orch(tmp_path, monkeypatch, SUPERMARKET)
    bo.reopen_connections()
    assert bo._schema_norm is None
    assert bo._routine_agent is None
    assert bo._nudge_agent is None
    assert bo._watchdog is not None  # the kiosk keeps watchdog (correct to rebuild)


# ────────────────────────────────────────────────────────────────────────────
# T4 — dependency-closure fail-loud (D4)
# ────────────────────────────────────────────────────────────────────────────

def test_t4_dep_closure_fail_loud() -> None:
    """T4 — a profile registering `schema` without `embed` fails LOUD at resolve
    (schema's inter-agent dep is embed)."""
    with pytest.raises(ProfileError):
        _resolve({"profile": "x", "agents": ["schema", "triage"]})
    # the closed counterpart resolves fine
    out = _resolve({"profile": "x", "agents": ["schema", "embed", "triage"]})
    assert out["ACTIVE_AGENTS"] == frozenset({"schema", "embed", "triage"})


# ────────────────────────────────────────────────────────────────────────────
# T5 — AST completeness ratchet (structural, INVERSE-CHECK FORALL; §11)
# ────────────────────────────────────────────────────────────────────────────

def _self_attr(node: ast.AST) -> "str | None":
    """Return X if node is `self._X` (Attribute(value=Name('self'), attr='_X'))."""
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "self":
        return node.attr
    return None


def _test_references_attr(test_node: ast.AST, attr: str) -> bool:
    return any(_self_attr(n) == attr for n in ast.walk(test_node))


def _is_guarded(node: ast.AST, attr: str, parents: dict) -> bool:
    """A `self.<attr>.<method>` site is guarded if EITHER:
    (1) it is lexically nested under an `if` whose test references `self.<attr>`
        (the nested-if pattern), OR
    (2) its enclosing function has an `if self.<attr> is ...:` statement whose
        body is an early-out (return/continue/raise) — the early-return pattern.
    FORALL over ALL agent attributes, so a future 16th agent is auto-covered."""
    cur = node
    func = None
    while cur in parents:
        cur = parents[cur]
        if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func = cur
            break
        if isinstance(cur, ast.If) and _test_references_attr(cur.test, attr):
            return True  # clause 1: nested under an if referencing self.<attr>
    if func is None:
        return False
    for n in ast.walk(func):  # clause 2: an early-out guard somewhere in the function
        if isinstance(n, ast.If) and _test_references_attr(n.test, attr):
            if any(isinstance(s, (ast.Return, ast.Continue, ast.Raise)) for s in n.body):
                return True
    return False


def test_t5_all_invocation_sites_guarded() -> None:
    """T5 — every `self._<agent>.<method>` call site in orchestrator.py sits
    inside a presence guard (FORALL over ALL registry attrs, not a hardcoded
    count). The structural net behind T2 — a future un-guarded site / new agent
    fails CI even if T2's surface list lags."""
    tree = ast.parse(_ORCH_PY.read_text(encoding="utf-8"))
    parents: dict = {}
    for p in ast.walk(tree):
        for c in ast.iter_child_nodes(p):
            parents[c] = p
    attrs = set(_ATTR.values())
    unguarded: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            attr = _self_attr(node.value)  # node is `self._x.<method>` → node.value is `self._x`
            if attr in attrs and not _is_guarded(node, attr, parents):
                unguarded.append(f"{attr} @ line {getattr(node, 'lineno', '?')}")
    assert not unguarded, (
        "SB.3 — these self._<agent>. invocation sites are NOT presence-guarded "
        "(an unregistered agent would crash on None):\n  " + "\n  ".join(unguarded)
    )


# ────────────────────────────────────────────────────────────────────────────
# T6 — hooks-as-list (D2)
# ────────────────────────────────────────────────────────────────────────────

def test_t6_hooks_are_lists() -> None:
    """T6 — every registry `hooks` is a list; household fires at ≥2 hooks (D2)."""
    for name, spec in AGENT_REGISTRY.items():
        assert isinstance(spec["hooks"], list), f"{name!r} hooks must be a list"
        assert all(isinstance(h, str) for h in spec["hooks"])
    assert len(AGENT_REGISTRY["household"]["hooks"]) >= 2


# ────────────────────────────────────────────────────────────────────────────
# T7 — registry is data (D4: no profiles/→core/ import)
# ────────────────────────────────────────────────────────────────────────────

def test_t7_registry_imports_nothing_from_core() -> None:
    """T7 — profiles/_registry.py imports NOTHING from core/ (name strings only)."""
    tree = ast.parse(_REGISTRY_PY.read_text(encoding="utf-8"))
    bad: list[str] = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            bad += [a.name for a in n.names if a.name == "core" or a.name.startswith("core.")]
        elif isinstance(n, ast.ImportFrom):
            mod = n.module or ""
            if mod == "core" or mod.startswith("core."):
                bad.append(mod)
    assert bad == [], f"profiles/_registry.py must not import core/: {bad}"


# ────────────────────────────────────────────────────────────────────────────
# T8 — topo-order
# ────────────────────────────────────────────────────────────────────────────

def test_t8_topo_embed_before_schema() -> None:
    """T8 — embed constructs before schema (the inter-agent edge)."""
    full = _topo_order(AGENT_BUNDLES["companion"])
    assert full.index("embed") < full.index("schema")
    partial = _topo_order(frozenset({"schema", "embed", "triage"}))
    assert partial.index("embed") < partial.index("schema")


# ────────────────────────────────────────────────────────────────────────────
# T9 — bundle shorthand (D3)
# ────────────────────────────────────────────────────────────────────────────

def test_t9_bundle_shorthand_resolution() -> None:
    """T9 — `agents: companion` → 15; explicit list → that set; absent → full."""
    assert _resolve({"agents": "companion"})["ACTIVE_AGENTS"] == frozenset(AGENT_REGISTRY)
    subset = ["triage", "embed", "schema"]
    assert _resolve({"agents": subset})["ACTIVE_AGENTS"] == frozenset(subset)
    assert _resolve({})["ACTIVE_AGENTS"] == frozenset(AGENT_REGISTRY)  # absent → full set


# ────────────────────────────────────────────────────────────────────────────
# T10 — ACTIVE_AGENTS from-import discipline (Lock 2)
# ────────────────────────────────────────────────────────────────────────────

def test_t10_active_agents_attribute_access_not_from_import() -> None:
    """T10 — the orchestrator reads config.ACTIVE_AGENTS by ATTRIBUTE access; it
    MUST NOT `from core.config import ACTIVE_AGENTS` (that binds the pre-apply
    default + silently ignores every profile). The apply writes the override
    under the ACTIVE_AGENTS key."""
    orch_src = _ORCH_PY.read_text(encoding="utf-8")
    tree = ast.parse(orch_src)
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and (n.module or "") == "core.config":
            assert "ACTIVE_AGENTS" not in [a.name for a in n.names], (
                "orchestrator must read config.ACTIVE_AGENTS by attribute, not from-import"
            )
    assert "config.ACTIVE_AGENTS" in orch_src
    # the loader keys the override as ACTIVE_AGENTS; config writes + defaults it.
    assert _resolve({"agents": "companion"}).get("ACTIVE_AGENTS") is not None
    cfg_src = _CONFIG_PY.read_text(encoding="utf-8")
    assert "ACTIVE_AGENTS" in cfg_src and 'frozenset(_SB3_AGENT_REGISTRY)' in cfg_src
