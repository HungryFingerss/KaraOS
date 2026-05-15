"""
tests/test_p072_read_migration_progress.py — P0.7.2 closure invariant.

Scans pipeline.py for remaining _active_sessions legacy reads and asserts
every non-exempt site is documented in ALLOWED_LEGACY_READS.

Exempt categories (never counted as violations):
  1. Shim-mirror passthrough  — line contains _shim_mirror_session_field_write
  2. Write operations         — _active_sessions[x]["key"] = value (assignment target)
  3. Comment lines            — stripped line starts with #
  4. Docstring lines          — detected via AST node ranges

ALLOWED_LEGACY_READS contains (lineno, rationale) for each accepted keep.
Adding a new entry here requires an explanation of why migration is not
possible.  The cap test prevents the allowlist from silently growing.
"""
from __future__ import annotations

import ast
import pathlib
import re

import pytest

PIPELINE_PATH = pathlib.Path(__file__).parent.parent / "pipeline.py"

# ---------------------------------------------------------------------------
# Documented keeps — every non-migratable legacy read with its rationale.
# lineno is the post-migration line number in pipeline.py.
# ---------------------------------------------------------------------------
ALLOWED_LEGACY_READS: frozenset[tuple[int, str]] = frozenset()

_ALLOWED_LINENOS: frozenset[int] = frozenset(ln for ln, _ in ALLOWED_LEGACY_READS)

# ---------------------------------------------------------------------------
# Sentinels and patterns
# ---------------------------------------------------------------------------
_SHIM_CALL = "_shim_mirror_session_field_write"

# Pattern A — _active_sessions[pid]["field"] direct subscript field read.
_RE_SUBSCRIPT = re.compile(
    r'_active_sessions\s*\[[^\]]+\]\s*\[\s*[\'"][^\'"]+[\'"]\s*\]'
)
# Pattern B — _active_sessions[pid].get("field"…) get-on-subscript.
_RE_GET_ON_SUB = re.compile(
    r'_active_sessions\s*\[[^\]]+\]\.get\s*\(\s*[\'"]'
)
# Pattern C — _active_sessions.get(pid, {}).get("field"…) outer-get + field-get.
# Intentionally does NOT match the (_active_sessions.get(pid) or {}).get(…)
# variant (that form has " or {}" between the two calls and is covered by
# _update_identity_evidence helper semantics — tracked separately).
_RE_GET_ON_OUTER = re.compile(
    r'_active_sessions\s*\.get\s*\([^)]+\)\s*\.get\s*\(\s*[\'"]'
)

# Write-site exclusion — _active_sessions[x]["key"] = (not ==).
_RE_WRITE = re.compile(
    r'_active_sessions\s*\[[^\]]+\]\s*\[\s*[\'"][^\'"]+[\'"]\s*\]\s*=[^=]'
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _docstring_lines(source: str) -> frozenset[int]:
    """Return all line numbers that belong to module/class/function docstrings."""
    tree = ast.parse(source)
    lines: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(
            node,
            (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef),
        ):
            continue
        if not node.body:
            continue
        first = node.body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            for ln in range(first.lineno, first.end_lineno + 1):
                lines.add(ln)
    return frozenset(lines)


def _scan_legacy_reads() -> list[tuple[int, str]]:
    """Return (lineno, stripped_line) for every unexempt legacy read in pipeline.py."""
    source = PIPELINE_PATH.read_text(encoding="utf-8")
    raw_lines = source.splitlines()
    doc_lines = _docstring_lines(source)
    hits: list[tuple[int, str]] = []
    for idx, raw in enumerate(raw_lines):
        lineno = idx + 1
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if lineno in doc_lines:
            continue
        # Shim-mirror passthrough — check this line AND the immediately preceding
        # non-empty line (multi-line _shim_mirror_session_field_write( calls have
        # the _active_sessions[...] argument on the continuation line).
        if _SHIM_CALL in raw:
            continue
        prev_nonempty = next(
            (raw_lines[j] for j in range(idx - 1, max(-1, idx - 4), -1)
             if raw_lines[j].strip()),
            "",
        )
        if _SHIM_CALL in prev_nonempty:
            continue
        if _RE_WRITE.search(raw):      # write target, not a read
            continue
        if (
            _RE_SUBSCRIPT.search(raw)
            or _RE_GET_ON_SUB.search(raw)
            or _RE_GET_ON_OUTER.search(raw)
        ):
            hits.append((lineno, stripped))
    return hits


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestReadMigrationProgress:

    def test_no_unallowed_legacy_reads(self):
        """All remaining legacy reads must be documented in ALLOWED_LEGACY_READS."""
        violations = [
            (ln, src)
            for ln, src in _scan_legacy_reads()
            if ln not in _ALLOWED_LINENOS
        ]
        assert not violations, (
            "Unmigrated _active_sessions reads found that are NOT in ALLOWED_LEGACY_READS.\n"
            "Either migrate them to peek_snapshot() or add them to the allowlist with rationale.\n"
            + "\n".join(f"  L{ln}: {src}" for ln, src in violations)
        )

    def test_allowlist_has_no_stale_entries(self):
        """Every lineno in ALLOWED_LEGACY_READS must still be a real legacy read.

        If a site was migrated, remove it from the allowlist.
        """
        found_lines = frozenset(ln for ln, _ in _scan_legacy_reads())
        stale = _ALLOWED_LINENOS - found_lines
        assert not stale, (
            f"ALLOWED_LEGACY_READS contains stale line numbers (site was migrated or "
            f"line moved without updating the allowlist): {sorted(stale)}\n"
            "Remove or renumber the stale entries."
        )

    def test_allowlist_size_is_bounded(self):
        """Allowlist must not grow beyond the declared cap without review."""
        cap = 0
        assert len(ALLOWED_LEGACY_READS) <= cap, (
            f"ALLOWED_LEGACY_READS has {len(ALLOWED_LEGACY_READS)} entries (cap={cap}). "
            "New keeps require a separate reviewer sign-off and an updated rationale."
        )
