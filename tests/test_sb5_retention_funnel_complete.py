"""SB.5 §4.a — method-AGNOSTIC exhaustiveness scanner for the retention/enrollment gate.

Per `karaos-org-discussions/solidify-base/SB5-1-plan-v2.md` §2 (PI-B) + the
2026-06-21 architect ratification. This is the ONLY net that catches a SECONDARY
writer the §4.b grow-then-purge behavioral leg is structurally blind to (e.g.
`promote_shadow_to_confirmed`, which only fires on a mention→meet→face-confirm
scenario the simulated encounter never exercises). It therefore cannot itself be
vacuous — hence the self-tests on the detector machinery (A6/A7) route through the
SAME helpers the production scan uses.

The contract (FORALL row-creating SQL write):
- Scan `core/db.py` + `core/brain_agent/memory/store.py` — the PERSONAL write
  surface, proven by the developer Pass-3 UNBOUNDED scan (Plan v2 §5 Step-1).
- Find every row-creating write — `INSERT INTO` / `INSERT OR IGNORE INTO` /
  `INSERT OR REPLACE INTO` / bare `REPLACE INTO`, dotted-`schema.table`-aware
  (Note-A: `INSERT INTO archive.conversation_log`). VERB-unbounded, keyed on the
  target TABLE, not a list of method names (a method-name allowlist would inherit
  the v1 undercount + the Finding-A mis-attribution and go vacuous on the next
  sibling).
- Classify each target against the exhaustive PERSONAL (17) / SYSTEM (7) partition.
  A target in NEITHER set → RED ("unclassified table — is it personal?"), forcing a
  human classification decision on every future table (the archive / room_summaries
  lesson made structural).
- Assert every PERSONAL write lives in a method that consults SOME gate
  (`config.ENROLLMENT_MODE` or `config.RETENTION_MODE`). §4.a stays "consults SOME
  gate" — robust, catches the UNGATED case; the §4.b concierge behavioral leg is
  the proof of the RIGHT (per-axis) gate.

Method-AGNOSTIC: the scan keys on the INSERT-target table + the enclosing-method
gate-consultation, never on a fixed set of 19 method names. A future 18th
personal-table INSERT, or a new ungated writer of an existing personal table, → RED
naming the file:line:method.

AST (not source-substring): the gate-consultation check inspects `config.X_MODE`
ast.Attribute nodes, so a docstring/comment mentioning the gate name cannot satisfy
it — the repeated AST-beats-substring lesson (P0.S12 A1, P0.S11 A5, P0.R3 A2).
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import ast
import re
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# --- The 2-file PERSONAL write surface (Plan v2 §2; unbounded-scan-proven) ---
_DB_PY = REPO_ROOT / "core" / "db.py"
_STORE_PY = REPO_ROOT / "core" / "brain_agent" / "memory" / "store.py"
_SCAN_FILES = (_DB_PY, _STORE_PY)

# --- The exhaustive PERSONAL / SYSTEM table partition (Plan v2 §1, Finding A) ---
# 17 personal tables / 20 personal INSERT statements / 19 distinct writer methods.
# `archive.conversation_log` is the dotted ATTACH-alias form (Note-A) — listed as the
# exact token AND covered by `conversation_log` (the live faces.db table) for the
# base-name fallback in `_classify`.
PERSONAL_TABLES = frozenset(
    {
        # faces.db (7)
        "persons",
        "embeddings",
        "voice_embeddings",
        "conversation_log",
        "silent_observations",
        "visitor_log",
        "archive.conversation_log",  # dotted ATTACH-alias (db.py archive move) — Note-A
        # brain.db (10)
        "knowledge",
        "prompt_prefs",
        "household_facts",
        "inter_person_relationships",
        "shadow_persons",
        "social_mentions",
        "episodes",
        "room_summaries",
        "presence_log",
        "proactive_nudges",
    }
)

# 7 SYSTEM tables — correctly NOT personal, correctly ungated. Note `schema_catalog`
# is incidentally skipped under ephemeral by the `store_knowledge` method-top gate
# (architect §91 ruling: harmless, NOT a partition violation — it is classified
# SYSTEM and is not a §4.a gate TARGET).
SYSTEM_TABLES = frozenset(
    {
        "system_identity",  # faces.db
        "brain_state",  # brain.db
        "schema_catalog",
        "agent_log",
        "predicate_stats",
        "watchdog_alerts",
        "intent_divergences",
    }
)

# Verb-unbounded + dotted-aware row-creating-write matcher (Plan v2 §2 amendment).
# Group 1 = the INSERT/REPLACE target table token (may be dotted `schema.table`).
_WRITE_RE = re.compile(
    r"\b(?:INSERT(?:\s+OR\s+(?:IGNORE|REPLACE))?|REPLACE)\s+INTO\s+([\w.]+)",
    re.IGNORECASE,
)

_GATE_ATTRS = frozenset({"ENROLLMENT_MODE", "RETENTION_MODE"})

# Sentinel substituted for f-string interpolations so a dynamic table name
# (`f"INSERT INTO {tbl}"`) does NOT silently capture a real table — it instead
# yields no `[\w.]+` match (the documented static-scan limitation; the §4.b
# behavioral leg + the full-suite run are the completeness backstop).
_FSTRING_HOLE = "\x00"


def _string_value(node: ast.AST) -> "str | None":
    """The string content of a Constant or the literal-parts of an f-string.

    Implicit string concatenation (the `INSERT INTO archive.conversation_log `
    + `(cols) ` + `SELECT ...` shape at db.py:336) is merged by the parser into a
    single `ast.Constant`, so this surfaces the full dotted token. f-string
    interpolations become `_FSTRING_HOLE` so dynamic table names don't false-capture.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        for v in node.values:
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                parts.append(v.value)
            else:
                parts.append(_FSTRING_HOLE)
        return "".join(parts)
    return None


def _iter_sql_writes(tree: ast.Module) -> "list[tuple[str, int]]":
    """Every (target_table_token, lineno) for a row-creating write in the tree.

    Walks ALL string constants / f-strings (method-agnostic — never trusts a method
    name or a count). A single string may carry multiple writes (defensive)."""
    out: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        s = _string_value(node)
        if not s or "INTO" not in s.upper():
            continue
        for m in _WRITE_RE.finditer(s):
            out.append((m.group(1), getattr(node, "lineno", -1)))
    return out


def _funcdefs(tree: ast.Module) -> "list[ast.AST]":
    return [
        n
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def _enclosing_funcdef(funcdefs: "list[ast.AST]", lineno: int) -> "ast.AST | None":
    """The INNERMOST FunctionDef/AsyncFunctionDef spanning `lineno` (or None at
    module scope). Innermost = smallest spanning range → the actual method, not its
    class or an outer wrapper."""
    best = None
    best_span = None
    for fn in funcdefs:
        start = fn.lineno
        end = getattr(fn, "end_lineno", start)
        if start <= lineno <= end:
            span = end - start
            if best_span is None or span < best_span:
                best, best_span = fn, span
    return best


def _func_consults_gate(funcdef: "ast.AST | None") -> bool:
    """True if the method body references `config.ENROLLMENT_MODE` or
    `config.RETENTION_MODE` as an attribute access (AST — not a docstring/comment)."""
    if funcdef is None:
        return False
    for n in ast.walk(funcdef):
        if (
            isinstance(n, ast.Attribute)
            and n.attr in _GATE_ATTRS
            and isinstance(n.value, ast.Name)
            and n.value.id == "config"
        ):
            return True
    return False


def _classify(token: str) -> str:
    """personal / system / unclassified. Exact-token first (handles the dotted
    `archive.conversation_log`), then base-name-after-last-dot fallback (a future
    `archive.<table>` classifies by `<table>`)."""
    if token in PERSONAL_TABLES:
        return "personal"
    if token in SYSTEM_TABLES:
        return "system"
    base = token.rsplit(".", 1)[-1]
    if base in PERSONAL_TABLES:
        return "personal"
    if base in SYSTEM_TABLES:
        return "system"
    return "unclassified"


def _scan_file(path: Path) -> "list[tuple[str, int]]":
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return _iter_sql_writes(tree)


# --------------------------------------------------------------------------- #
# A1 — scope + partition shape
# --------------------------------------------------------------------------- #
def test_scan_files_exist_and_partition_is_well_formed() -> None:
    for p in _SCAN_FILES:
        assert p.is_file(), f"§4.a scan scope file missing: {p}"
    assert len(PERSONAL_TABLES) == 17, "Plan v2 §1: 17 personal tables (incl. dotted archive)"
    assert len(SYSTEM_TABLES) == 7, "Plan v2 §1: 7 system tables"
    overlap = PERSONAL_TABLES & SYSTEM_TABLES
    assert not overlap, f"personal/system partition must be disjoint; overlap={overlap}"


# --------------------------------------------------------------------------- #
# A2 — the partition is exhaustive (every production write target classifies)
# --------------------------------------------------------------------------- #
def test_no_unclassified_write_target_in_scope() -> None:
    unclassified: list[str] = []
    for path in _SCAN_FILES:
        for token, lineno in _scan_file(path):
            if _classify(token) == "unclassified":
                unclassified.append(f"{path.relative_to(REPO_ROOT)}:{lineno} INTO {token}")
    assert not unclassified, (
        "Unclassified row-creating write target(s) — is it personal? Add to "
        "PERSONAL_TABLES (and gate the writer) or SYSTEM_TABLES:\n  "
        + "\n  ".join(unclassified)
    )


# --------------------------------------------------------------------------- #
# A3 — THE core §4.a invariant: every personal write is in a gated method
# --------------------------------------------------------------------------- #
def test_every_personal_write_lives_in_a_gated_method() -> None:
    offenders: list[str] = []
    for path in _SCAN_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        funcdefs = _funcdefs(tree)
        for token, lineno in _iter_sql_writes(tree):
            if _classify(token) != "personal":
                continue
            fn = _enclosing_funcdef(funcdefs, lineno)
            if not _func_consults_gate(fn):
                where = fn.name if fn is not None else "<module scope>"
                offenders.append(
                    f"{path.relative_to(REPO_ROOT)}:{lineno} INTO {token} "
                    f"(method `{where}` does not consult config.ENROLLMENT_MODE / "
                    f"config.RETENTION_MODE)"
                )
    assert not offenders, (
        "PERSONAL-data write(s) in an UNGATED method — the SB.5 retention/enrollment "
        "gate is the load-bearing privacy fix:\n  " + "\n  ".join(offenders)
    )


# --------------------------------------------------------------------------- #
# A4 — non-vacuity against PRODUCTION (the scan actually finds the writes)
# --------------------------------------------------------------------------- #
def test_scanner_is_non_vacuous_against_production() -> None:
    personal = 0
    system = 0
    found_tokens: set[str] = set()
    for path in _SCAN_FILES:
        for token, _lineno in _scan_file(path):
            found_tokens.add(token)
            kind = _classify(token)
            if kind == "personal":
                personal += 1
            elif kind == "system":
                system += 1
    # 20 personal INSERT statements + 8 system at the 2026-06-21 baseline; assert a
    # generous floor (NOT an exact count — §4.a never trusts a count, Plan v2 §62).
    assert personal >= 17, f"expected >= 17 personal writes, scan found {personal}"
    assert system >= 4, f"expected >= 4 system writes, scan found {system}"
    # Note-A: the dotted ATTACH-alias form must be surfaced by the dotted-aware regex
    # against real production code — proven, not assumed.
    assert "archive.conversation_log" in found_tokens, (
        "dotted-aware regex failed to surface `INSERT INTO archive.conversation_log` "
        "(db.py archive move) — the Note-A dotted-target path is not covered"
    )


# --------------------------------------------------------------------------- #
# A5 — the partition split is real (system tables are present, not all-personal)
# --------------------------------------------------------------------------- #
def test_known_system_tables_are_found_and_classified_system() -> None:
    found_system: set[str] = set()
    for path in _SCAN_FILES:
        for token, _lineno in _scan_file(path):
            if _classify(token) == "system":
                found_system.add(token if token in SYSTEM_TABLES else token.rsplit(".", 1)[-1])
    # Anchors that MUST appear (else the scan or partition is silently broken):
    for anchor in ("system_identity", "brain_state", "schema_catalog"):
        assert anchor in found_system, (
            f"system anchor `{anchor}` not found among scanned writes — the scan or "
            f"the partition split is broken"
        )


# --------------------------------------------------------------------------- #
# A6 — detector self-test: the write-regex (same regex the production scan uses)
# --------------------------------------------------------------------------- #
def test_write_regex_self_test() -> None:
    def _targets(src: str) -> list[str]:
        return [m.group(1) for m in _WRITE_RE.finditer(src)]

    # Catches: plain / OR IGNORE / OR REPLACE / bare REPLACE / dotted.
    assert _targets("INSERT INTO knowledge (a) VALUES (1)") == ["knowledge"]
    assert _targets("INSERT OR IGNORE INTO persons (id) VALUES (1)") == ["persons"]
    assert _targets("INSERT OR REPLACE INTO room_summaries (x) VALUES (1)") == ["room_summaries"]
    assert _targets("REPLACE INTO foo (x) VALUES (1)") == ["foo"]
    assert _targets("INSERT INTO archive.conversation_log (a) SELECT a") == [
        "archive.conversation_log"
    ]
    # `INSERT OR REPLACE` must NOT double-count as both an INSERT and a REPLACE match.
    assert _targets("INSERT OR REPLACE INTO room_summaries VALUES (1)") == ["room_summaries"]
    # Does NOT match read/update/delete (not row-creating).
    assert _targets("SELECT * FROM knowledge") == []
    assert _targets("UPDATE knowledge SET x = 1") == []
    assert _targets("DELETE FROM knowledge WHERE id = 1") == []


# --------------------------------------------------------------------------- #
# A7 — detector self-test: gate-consultation (AST, not source-substring)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "src,expected",
    [
        # retention gate present (early-return shape)
        (
            "def store_x(self):\n"
            "    if config.RETENTION_MODE == 'ephemeral':\n"
            "        return\n"
            "    self._conn.execute('INSERT INTO knowledge VALUES (1)')\n",
            True,
        ),
        # enrollment gate present (write-only-if shape, like add_stranger)
        (
            "def add_x(self):\n"
            "    if config.ENROLLMENT_MODE == 'persistent':\n"
            "        self._conn.execute('INSERT INTO persons VALUES (1)')\n",
            True,
        ),
        # no gate at all
        (
            "def store_x(self):\n"
            "    self._conn.execute('INSERT INTO knowledge VALUES (1)')\n",
            False,
        ),
        # docstring/comment ONLY mention — must NOT satisfy (AST robustness)
        (
            "def store_x(self):\n"
            "    '''gated on config.RETENTION_MODE elsewhere.'''\n"
            "    # config.ENROLLMENT_MODE is checked by the caller\n"
            "    self._conn.execute('INSERT INTO knowledge VALUES (1)')\n",
            False,
        ),
        # wrong attribute name on config — must NOT satisfy
        (
            "def store_x(self):\n"
            "    if config.SOME_OTHER_MODE == 'x':\n"
            "        return\n"
            "    self._conn.execute('INSERT INTO knowledge VALUES (1)')\n",
            False,
        ),
    ],
)
def test_gate_consult_self_test(src: str, expected: bool) -> None:
    tree = ast.parse(textwrap.dedent(src))
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef))
    assert _func_consults_gate(fn) is expected
