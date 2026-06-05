"""
P1.A1-slice + P0.X Gap 2 — layering invariants for pipeline.py and brain_agent.py.

pipeline.py must NOT bypass the owning class's API contract by reaching into
private attributes of core/* class instances.

brain_agent.py BrainOrchestrator must NOT access self._brain_db._conn directly;
all raw _conn queries must go through BrainDB's public methods (P0.X Gap 3).

Forbidden patterns detected by two complementary checks:

  DIRECT (simple Name._attr scan — catches local-variable form):
    db._conn              → use db.close() / db.transaction()
    _brain_orchestrator._brain_db
                          → use _brain_orchestrator.brain_db (public property)
    _brain_db._conn       → use a BrainDB public method (P0.X Gap 3)

  CHAINED (self._brain_db._conn pattern in brain_agent.py):
    self._brain_db._conn  → use a BrainDB public method
    Caught by _find_chained_brain_db_conn() which walks for the specific
    3-node chain Attribute("_conn", Attribute("_brain_db", Name("self"))).
    The simple detector cannot catch this because the outer value is not a
    plain Name but a nested Attribute.

Rejected from scope:

  - Module-level dicts (_active_sessions, _persons_in_frame, etc.) — not class
    attributes; pipeline.py's own module-level state, not layering violations.
  - Builtin/third-party private attributes (np.array._dtype, etc.) — out of
    our control.
  - Single-underscore names that ARE the public API by convention (e.g.,
    _build_room_block, _execute_tool) — naming convention, not visibility.
  - Dunder access (__class__, __name__, etc.) — Python protocol, fair game.
  - BrainDB._conn inside BrainDB itself — that is the owner accessing its own
    private field; the rule applies to OUTSIDERS reaching in.

DLL-safe: reads source files via Path + ast.parse(); no pipeline import.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PIPELINE_PATH = REPO_ROOT / "pipeline.py"
BRAIN_AGENT_PATH = REPO_ROOT / "core" / "brain_agent" / "__init__.py"

# Forbidden: (instance_name, attribute_name) pairs that bypass owning class API.
# Public alternatives:
#   db._conn              → db.close() / db.transaction()       (FaceDB)
#   _brain_orchestrator._brain_db
#                         → _brain_orchestrator.brain_db        (public property)
#   _brain_db._conn       → a BrainDB public method             (P0.X Gap 3)
FORBIDDEN_LAYERING_ACCESSES: tuple[tuple[str, str], ...] = (
    ("db", "_conn"),                      # FaceDB — use db.close() / db.transaction()
    ("_brain_orchestrator", "_brain_db"), # BrainOrchestrator — use .brain_db property
    ("_brain_db", "_conn"),               # P0.X: direct _brain_db._conn local-var form
)


def _find_layering_violations(source: str, source_name: str = "pipeline.py") -> list[str]:
    """Scan AST for <instance>._<attr> access matching any forbidden pair.

    Only catches patterns where the instance is a plain Name node (direct
    variable access). Chained access like self._brain_db._conn is caught
    separately by _find_chained_brain_db_conn().
    """
    tree = ast.parse(source)
    failures: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        if not isinstance(node.value, ast.Name):
            continue

        instance_name = node.value.id
        attribute_name = node.attr

        for (forbidden_instance, forbidden_attr) in FORBIDDEN_LAYERING_ACCESSES:
            if instance_name == forbidden_instance and attribute_name == forbidden_attr:
                line = getattr(node, "lineno", "?")
                failures.append(
                    f"  - {source_name}:{line}: {instance_name}.{attribute_name} "
                    f"bypasses owning class API"
                )
                break

    return failures


def _find_chained_brain_db_conn(source: str) -> list[str]:
    """Detect self._brain_db._conn chained access (3-node chain).

    The simple Name._attr detector cannot catch this because the outer
    value node is Attribute("_brain_db", Name("self")), not a plain Name.
    Specifically catches:
        Attribute(attr="_conn",
            value=Attribute(attr="_brain_db",
                value=Name(id="self")))
    """
    tree = ast.parse(source)
    failures: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        if node.attr != "_conn":
            continue
        if not isinstance(node.value, ast.Attribute):
            continue
        if node.value.attr != "_brain_db":
            continue
        if not isinstance(node.value.value, ast.Name):
            continue
        if node.value.value.id != "self":
            continue
        line = getattr(node, "lineno", "?")
        failures.append(
            f"  - brain_agent.py:{line}: self._brain_db._conn bypasses BrainDB "
            f"public API — add a BrainDB public method and call it instead"
        )

    return failures


# ── pipeline.py layering test ─────────────────────────────────────────────────

def test_no_layering_violations_in_pipeline():
    """Pipeline.py must use public methods of core/* classes, not reach into their
    private attributes. The forbidden pairs are explicit (see
    FORBIDDEN_LAYERING_ACCESSES). Add new pairs to that tuple if a future audit
    surfaces them; do NOT broaden the rule to 'any underscore access.'
    """
    source = PIPELINE_PATH.read_text(encoding="utf-8")
    failures = _find_layering_violations(source, "pipeline.py")

    assert not failures, (
        f"P1.A1-slice invariant violated — "
        f"{len(failures)} layering boundary breach(es):\n"
        + "\n".join(failures)
        + "\n\nFix: add a public wrapper method/property on the owning class, "
        "replace the direct access at the call site. Update "
        "FORBIDDEN_LAYERING_ACCESSES if you remove a pair."
    )


# ── brain_agent.py layering test (P0.X Gap 2) ─────────────────────────────────

def test_no_layering_violations_in_brain_agent():
    """brain_agent.py must not contain direct or chained self._brain_db._conn access.

    P0.X Gap 3 replaced all raw _conn calls with BrainDB public methods.
    Two complementary checks run:
      1. Simple direct-pair scan for _brain_db._conn (local-variable form).
      2. Chained scan for self._brain_db._conn (the form previously in
         BrainOrchestrator._ensure_graph_sync and __init__).

    If this test fails after a new BrainOrchestrator method is added, add the
    query to BrainDB as a public method and call it instead.
    """
    source = BRAIN_AGENT_PATH.read_text(encoding="utf-8")
    failures = _find_layering_violations(source, "brain_agent.py")
    failures += _find_chained_brain_db_conn(source)

    assert not failures, (
        f"P0.X Gap 2 layering invariant violated — "
        f"{len(failures)} _brain_db._conn access(es) in brain_agent.py:\n"
        + "\n".join(failures)
        + "\n\nFix: add a public method to BrainDB for this query and replace "
        "the raw _conn call at the violation site."
    )


# ── simple detector self-tests ────────────────────────────────────────────────

@pytest.mark.parametrize("source, expect_violation", [
    # Direct violation: db._conn access via method call
    ("def f():\n    db._conn.close()\n", True),
    # Direct violation: db._conn (attribute read, no call)
    ("def f():\n    x = db._conn\n", True),
    # Direct violation: _brain_orchestrator._brain_db access
    ("def f():\n    _brain_orchestrator._brain_db.get_recent_visitor_alerts()\n", True),
    # Direct violation: _brain_orchestrator._brain_db attribute read
    ("def f():\n    x = _brain_orchestrator._brain_db\n", True),
    # Direct violation: _brain_db._conn (P0.X Gap 2 pair)
    ("def f():\n    _brain_db._conn.execute('SELECT 1')\n", True),
    # OK: db.close() is the public wrapper
    ("def f():\n    db.close()\n", False),
    # OK: _brain_orchestrator.brain_db is the public property
    ("def f():\n    _brain_orchestrator.brain_db.get_recent_visitor_alerts()\n", False),
    # OK: module-level dict — not a class instance attribute
    ("def f():\n    _active_sessions[pid] = {}\n", False),
    # OK: dunder access (Python protocol)
    ("def f():\n    name = obj.__class__.__name__\n", False),
    # OK: variable name not in forbidden list
    ("def f():\n    some_other_obj._conn\n", False),
    # OK: _brain_orchestrator accessing a public attribute (no underscore)
    ("def f():\n    _brain_orchestrator.notify()\n", False),
])
def test_detector_against_synthetic_sources(source, expect_violation):
    """Detector must catch only the explicit forbidden pairs, not every
    underscore access. Synthetic cases verify both directions.
    """
    failures = _find_layering_violations(source)
    actual = len(failures) > 0
    assert actual == expect_violation, (
        f"Detector mismatch on:\n{source}\n"
        f"expected violation={expect_violation}, got {actual}, "
        f"failures={failures}"
    )


# ── chained detector self-tests (P0.X Gap 2) ─────────────────────────────────

@pytest.mark.parametrize("source, expect_violation", [
    # Chained violation: self._brain_db._conn (the exact shape cleaned up in Gap 3)
    (
        "class A:\n    def f(self):\n        self._brain_db._conn.execute('q')\n",
        True,
    ),
    # Chained violation: self._brain_db._conn attribute read
    (
        "class A:\n    def f(self):\n        x = self._brain_db._conn\n",
        True,
    ),
    # OK: self._brain_db.public_method() — no _conn access
    (
        "class A:\n    def f(self):\n        self._brain_db.get_graph_schema_version()\n",
        False,
    ),
    # OK: chained but different attribute — not _conn
    (
        "class A:\n    def f(self):\n        self._brain_db._cursor\n",
        False,
    ),
    # OK: _conn on a different intermediate attribute
    (
        "class A:\n    def f(self):\n        self._face_db._conn.execute('q')\n",
        False,
    ),
    # OK: _conn on a non-self outer name
    (
        "class A:\n    def f(self):\n        other._brain_db._conn.execute('q')\n",
        False,
    ),
])
def test_chained_detector_against_synthetic_sources(source, expect_violation):
    """Chained detector must catch self._brain_db._conn specifically.
    Adjacent patterns (different attr, different outer name) must not fire.
    """
    failures = _find_chained_brain_db_conn(source)
    actual = len(failures) > 0
    assert actual == expect_violation, (
        f"Chained detector mismatch on:\n{source}\n"
        f"expected violation={expect_violation}, got {actual}, "
        f"failures={failures}"
    )
