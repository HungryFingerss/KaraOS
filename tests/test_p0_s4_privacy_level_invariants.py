"""tests/test_p0_s4_privacy_level_invariants.py — P0.S4 privacy-level invariants.

D1 (write-path validation) tests land in Phase 4. This file covers:

  - **D2** (1 test) — module-wide AST + regex scan of ``core/brain_agent.py``;
    every privacy_level tier value referenced in SQL/Cypher string literals
    MUST be a member of ``PRIVACY_LEVELS``. Catches drift if a future refactor
    renames a tier in ``config.PRIVACY_LEVELS`` without updating the
    hardcoded SQL literals.

  - **D3** (2 tests + parametrize) — ``PRIVACY_LEVEL_STATIC_MAP`` value
    invariant. Each of the 22 entries MUST map to a tier ∈ ``PRIVACY_LEVELS``.
    Companion sanity check: ``PRIVACY_LEVEL_DEFAULT`` itself ∈ ``PRIVACY_LEVELS``
    (catches typos like ``PRIVACY_LEVEL_DEFAULT = "personnal"``).

Spec: tests/p0_s4_plan_v1.md §1.P1 + §2 (D2 + D3); tests/p0_s4_plan_v2.md §1
(corrected site enumeration after Plan v1 auditor review).
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from core import config

# P0.S7 D2 — module-level privacy_critical marker; all tests in this file
# verify the privacy_level whitelist invariant (P0.S4 D1-D3).
pytestmark = pytest.mark.privacy_critical


_REPO_ROOT = Path(__file__).resolve().parent.parent
# P1.A1 SP-2 C2: the privacy SQL-tier literals (_visibility_clause +
# _assert_valid_privacy_level error) moved to privacy.py; GraphDB Cypher +
# agent privacy_level= constructions stay in __init__.py. Scan BOTH so no
# tier literal escapes the drift-protection invariant.
_BRAIN_AGENT_FILES = [
    _REPO_ROOT / "core" / "brain_agent" / "__init__.py",
    _REPO_ROOT / "core" / "brain_agent" / "privacy.py",
    _REPO_ROOT / "core" / "brain_agent" / "memory" / "graph.py",
    _REPO_ROOT / "core" / "brain_agent" / "agents" / "extraction.py",
    _REPO_ROOT / "core" / "brain_agent" / "agents" / "nudge.py",
]

# Match ``privacy_level <op> 'tier'`` where ``<op>`` ∈ {=, !=, <>, IN, NOT IN}.
# Capture the tier literal. Allows quoted-list shapes like
# ``privacy_level IN ('public', 'household')`` via repeated ``finditer``
# (the first capture per match; future expansion to multi-capture per Plan v1
# §1.P1 known-limitation if such shapes are added later).
_SQL_TIER_RE = re.compile(
    r"privacy_level\s*(?:=|!=|<>|\bIN\b|\bNOT\s+IN\b)\s*\(?\s*'([^']+)'"
)


# ───────────────────────────────────────────────────────────────────────
# D2 — SQL/Cypher literal drift invariant (1 test)
# ───────────────────────────────────────────────────────────────────────


def test_brain_agent_sql_tier_literals_are_all_valid():
    """D2 — every ``privacy_level`` tier value referenced in
    ``core/brain_agent.py`` SQL string literals MUST be a member of
    ``PRIVACY_LEVELS``.

    Catches drift if a future refactor renames a tier in
    ``config.PRIVACY_LEVELS`` without updating the hardcoded SQL literals.

    Scope (Plan v1 §1.P2 expansion): scans the ENTIRE module via
    ``ast.parse + ast.walk``, not just ``_visibility_clause`` alone.
    Coverage (per Plan v2 §1 corrected enumeration):

      Code sites (7) — all MUST land in ``PRIVACY_LEVELS``:
        line 538  ``_visibility_clause`` (best_friend `!=`)
        line 543  ``_visibility_clause`` (non-bf `=` public)
        line 544  ``_visibility_clause`` (non-bf `=` personal)
        line 3694 ``find_shared_entities`` (Cypher `<>` system_only)
        line 3696 ``find_shared_entities`` (Cypher `=` public)
        line 3804 ``find_shared_entities`` (Cypher `=` public, 2nd)
        line 6156 ``run_cross_person_inference`` (`!=` system_only)

      Doc mentions (5) — naturally cite valid tiers in docstrings:
        line 525  ``_visibility_clause`` docstring
        line 3538 Kuzu schema comment
        line 3772 ``find_shared_entities`` docstring
        line 3795 ``find_shared_entities`` docstring (P0.S7.D-B)
        line 4443 ``extract_assistant_room_turn`` docstring (D6)

    Line numbers drift over time — the test is structurally line-number-
    agnostic (regex finds the SQL shape via ``ast.walk`` over string
    constants; doesn't reference line numbers in its logic). See Plan v2
    §6 known-limitation block.
    """
    violations: list[tuple[int, str]] = []
    for _bf in _BRAIN_AGENT_FILES:
        tree = ast.parse(_bf.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                continue
            for m in _SQL_TIER_RE.finditer(node.value):
                tier = m.group(1)
                if tier not in config.PRIVACY_LEVELS:
                    # ``node.lineno`` is the line of the string literal in source.
                    violations.append((node.lineno, tier))

    assert not violations, (
        "brain_agent.py SQL/Cypher string literals reference tier values "
        "NOT in PRIVACY_LEVELS:\n"
        + "\n".join(f"  line {ln}: tier {t!r}" for ln, t in violations)
        + f"\nValid tiers: {sorted(config.PRIVACY_LEVELS)}.\n"
        "If a tier was renamed in config.PRIVACY_LEVELS, update the SQL "
        "literal too. If a new tier was added, this is the structural "
        "drift-protection invariant catching the partial update — add the "
        "new tier to the SQL OR remove the obsolete reference."
    )


# ───────────────────────────────────────────────────────────────────────
# D3 — PRIVACY_LEVEL_STATIC_MAP + PRIVACY_LEVEL_DEFAULT invariants
#       (2 tests + parametrize fan-out)
# ───────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("attribute", "tier"),
    sorted(config.PRIVACY_LEVEL_STATIC_MAP.items()),
    ids=sorted(config.PRIVACY_LEVEL_STATIC_MAP.keys()),
)
def test_static_map_value_is_valid_tier(attribute: str, tier: str):
    """D3 — every value in ``PRIVACY_LEVEL_STATIC_MAP`` MUST be a member of
    ``PRIVACY_LEVELS``.

    Parametrized over ALL 22 entries (count grew implicitly with the
    fan-out shape locked at Plan v1 §2). Each entry surfaces as a
    distinct test ID by attribute name, so a typo (e.g.,
    ``"personnal"`` instead of ``"personal"``) fails ONLY that entry's
    test with the attribute name in the failure message.

    Catches the case where someone adds a new attribute to the static
    map but the value collides with a tier that doesn't exist (legacy
    ``"private"`` 2-tier name, typo, copy-paste artifact).
    """
    assert tier in config.PRIVACY_LEVELS, (
        f"PRIVACY_LEVEL_STATIC_MAP[{attribute!r}] = {tier!r} is NOT a "
        f"member of PRIVACY_LEVELS. Valid tiers: "
        f"{sorted(config.PRIVACY_LEVELS)}. If this is a typo (e.g., "
        f"'personnal' for 'personal'), fix the static map. If the tier "
        f"name was renamed in PRIVACY_LEVELS, update this entry to match. "
        f"Legacy 'private' (pre-Session 95 3A.4.5) should map to 'personal'."
    )


def test_static_map_default_tier_is_valid():
    """D3 — ``PRIVACY_LEVEL_DEFAULT`` itself MUST be a member of
    ``PRIVACY_LEVELS``.

    Sanity check: catches the case where the default constant is
    misnamed (e.g., ``PRIVACY_LEVEL_DEFAULT = "personnal"`` typo).
    Without this guard, every fail-closed fallback path (the
    ``_classify_privacy_level`` LLM-failure branch, the
    ``Extraction.privacy_level`` field default) would silently produce
    invisible rows.
    """
    assert config.PRIVACY_LEVEL_DEFAULT in config.PRIVACY_LEVELS, (
        f"PRIVACY_LEVEL_DEFAULT = {config.PRIVACY_LEVEL_DEFAULT!r} is NOT "
        f"a member of PRIVACY_LEVELS. Valid tiers: "
        f"{sorted(config.PRIVACY_LEVELS)}. The fail-closed default tier "
        f"would write structurally invisible rows on every classifier "
        f"failure path. Likely cause: typo in core/config.py."
    )


# ───────────────────────────────────────────────────────────────────────
# D1 — store_knowledge + _create_edge write-path validation (5 tests)
# Locked exact substrings per Plan v1 §1.P4.
# ───────────────────────────────────────────────────────────────────────


@pytest.fixture
def brain_db(tmp_path):
    """Fresh ``BrainDB`` instance on a tmp path. Closes the connection on
    teardown so Windows can clean up the SQLite file.
    """
    from core.brain_agent import BrainDB
    db = BrainDB(tmp_path / "brain.db")
    try:
        yield db
    finally:
        db._conn.close()


def _make_extraction(**overrides):
    """Build an ``Extraction`` with sensible test defaults. Overrides win."""
    from core.brain_agent import Extraction
    kwargs = dict(
        entity="TestEntity",
        entity_type="person",
        attribute="test_attr",
        value="test_value",
        confidence=0.9,
        is_temporal=False,
        valid_for_hours=None,
    )
    kwargs.update(overrides)
    return Extraction(**kwargs)


def test_store_knowledge_rejects_invalid_privacy_level(brain_db):
    """D1 test 1 — ``Extraction(privacy_level="not_a_real_tier")`` reaches
    ``store_knowledge`` → ``ValueError`` with the 3 P4-locked substrings.

    Motivating-failure regression guard: prior to P0.S4 D1, an invalid
    tier would write a row that's structurally invisible to every
    retrieval site (the visibility clause has no predicate matching
    invalid tiers). The fail-loud raise + traceback at the
    ``_poll_once`` wrapper makes the programmer error visible.
    """
    invalid = "not_a_real_tier"
    ext = _make_extraction(privacy_level=invalid)

    with pytest.raises(ValueError) as excinfo:
        brain_db.store_knowledge(
            [ext], turn_id=1, person_id="p1", agent="test_agent",
        )

    body = str(excinfo.value)
    assert "privacy_level" in body, (
        "ValueError body MUST name the field that holds the invalid value "
        "(operator searches the error for the field name)"
    )
    assert "PRIVACY_LEVELS" in body, (
        "ValueError body MUST name the constraint constant the operator "
        "must consult in core/config.py"
    )
    assert invalid in body, (
        f"ValueError body MUST contain the offending value {invalid!r} "
        "verbatim so the operator can grep for which extraction produced it"
    )


@pytest.mark.parametrize("tier", sorted(config.PRIVACY_LEVELS))
def test_store_knowledge_accepts_all_valid_tiers(brain_db, tier):
    """D1 test 2 (parametrized over 4 PRIVACY_LEVELS members) — each valid
    tier writes successfully + row visible via direct SQL query.

    Negative regression guard against an over-eager guard that rejects
    legitimate tiers. Every PRIVACY_LEVELS member must round-trip
    through ``store_knowledge`` without raising.
    """
    ext = _make_extraction(privacy_level=tier, attribute=f"attr_{tier}")

    # MUST NOT raise
    n = brain_db.store_knowledge(
        [ext], turn_id=100, person_id=f"pid_{tier}", agent="test_agent",
    )
    assert n == 1, "store_knowledge MUST return count=1 for a single valid Extraction"

    # Row MUST be visible via direct SQL query — privacy_level column
    # carries the tier verbatim
    rows = brain_db._conn.execute(
        "SELECT entity, attribute, value, privacy_level FROM knowledge "
        "WHERE source_turn_id = ? AND person_id = ?",
        (100, f"pid_{tier}"),
    ).fetchall()
    assert len(rows) == 1, (
        f"row for tier {tier!r} MUST persist; got {len(rows)} rows"
    )
    assert rows[0][3] == tier, (
        f"persisted privacy_level MUST be {tier!r}; got {rows[0][3]!r}"
    )


def test_store_knowledge_rejects_legacy_private_tier(brain_db):
    """D1 test 3 — ``Extraction(privacy_level="private")`` (the Session 95
    3A.4.5 migration's legacy 2-tier name) → ``ValueError`` with
    ``"private"`` verbatim + ``PRIVACY_LEVELS`` + all 4 valid tier names
    in some form (operator sees the valid set in the error).

    This IS the motivating-failure regression guard for the spec — the
    canonical drift case that produced invisible rows pre-P0.S4.
    """
    ext = _make_extraction(privacy_level="private")

    with pytest.raises(ValueError) as excinfo:
        brain_db.store_knowledge(
            [ext], turn_id=2, person_id="p1", agent="test_agent",
        )

    body = str(excinfo.value)
    assert "privacy_level" in body
    assert "private" in body, (
        "ValueError body MUST contain the literal legacy tier name 'private' "
        "verbatim — Session 95 3A.4.5 canonical regression case"
    )
    assert "PRIVACY_LEVELS" in body, (
        "ValueError body MUST name the constraint constant"
    )
    # All 4 valid tier names appear in the body via the sorted-list rendering
    for valid_tier in config.PRIVACY_LEVELS:
        assert valid_tier in body, (
            f"ValueError body MUST surface all valid tiers (operator "
            f"needs to see what's allowed); {valid_tier!r} missing"
        )


def test_create_edge_rejects_invalid_privacy_level(tmp_path):
    """D1 test 4 — same shape as test 1 but at the Kuzu ``_create_edge``
    write boundary. Verifies D1 extends to the parallel Kuzu storage
    path (Phase 0 §1 sideways recommendation, Plan v1 §1.P2 expansion).

    The validation guard fires BEFORE the Cypher execute, so the test
    doesn't need pre-seeded graph entities — the raise happens at the
    function entry.
    """
    from core.brain_agent import GraphDB

    graph = GraphDB(tmp_path / "brain_graph")
    try:
        invalid = "not_a_real_tier"
        with pytest.raises(ValueError) as excinfo:
            graph._create_edge(
                src="SrcEntity",
                tgt="TgtEntity",
                attribute="test_attr",
                value="test_value",
                confidence=0.9,
                is_temporal=False,
                valid_until=None,
                valid_at=None,
                invalidated=False,
                source_turn_id=1,
                created_at=0.0,
                privacy_level=invalid,
            )

        body = str(excinfo.value)
        assert "privacy_level" in body
        assert "PRIVACY_LEVELS" in body
        assert invalid in body, (
            f"ValueError body from _create_edge MUST contain the offending "
            f"value {invalid!r} verbatim"
        )
        # Forensic context — the helper's context= breadcrumb MUST surface
        # the Kuzu write site so the operator can distinguish brain.db vs
        # Kuzu validation failures in the log
        assert "GraphDB._create_edge" in body, (
            "ValueError body MUST identify GraphDB._create_edge as the "
            "write boundary (forensic disambiguation from store_knowledge)"
        )
    finally:
        graph.close()


def test_store_knowledge_default_extraction_passes_validation(brain_db):
    """D1 test 5 — ``Extraction()`` with no explicit ``privacy_level``
    kwarg uses the dataclass default ``PRIVACY_LEVEL_DEFAULT`` = ``"personal"``;
    ``store_knowledge`` MUST accept it without raising.

    Negative regression guard: ensures the dataclass default doesn't
    accidentally trigger D1's validation. The default IS in
    ``PRIVACY_LEVELS`` (catches the case where someone misnames the
    default constant — companion to ``test_static_map_default_tier_is_valid``
    above).
    """
    # Build Extraction WITHOUT specifying privacy_level — relies on the dataclass default
    ext = _make_extraction()  # _make_extraction omits privacy_level → field default applies
    assert ext.privacy_level == config.PRIVACY_LEVEL_DEFAULT, (
        "sanity check: Extraction default MUST equal PRIVACY_LEVEL_DEFAULT; "
        "if this fails, the dataclass default has drifted"
    )

    # MUST NOT raise
    n = brain_db.store_knowledge(
        [ext], turn_id=5, person_id="p_default", agent="test_agent",
    )
    assert n == 1

    # Persisted tier matches the default
    row = brain_db._conn.execute(
        "SELECT privacy_level FROM knowledge WHERE source_turn_id = ?",
        (5,),
    ).fetchone()
    assert row is not None
    assert row[0] == config.PRIVACY_LEVEL_DEFAULT
