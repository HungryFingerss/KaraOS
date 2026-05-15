"""
P0.1 — structural test: no raw "disputed" string comparisons outside _is_disputed().

Every check for person_type == "disputed" must route through _is_disputed().
Raw comparisons bypass any future enrichment of the helper.

Uses ast.parse() to locate _is_disputed() by line range — never imports pipeline.py,
avoiding the Windows torchaudio DLL crash (OSError 0xc0000139).

Allowlisted legitimate uses:
  - Inside _is_disputed() body (AST line-range exclusion)
  - core/config.py (enum/constant declarations — excluded entirely)
  - Literal["disputed"] type annotations (AST subscript detection)
  - UPPERCASE constant assignments containing "disputed" (AST assign detection)
  - Lines marked with # disputed-row-status (non-person_type domain uses,
    e.g. knowledge-row status columns in core/brain_agent.py)
"""
import ast
import re
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent
_PIPELINE_PY = _REPO_ROOT / "pipeline.py"
_CORE_DIR = _REPO_ROOT / "core"

# core/config.py is excluded entirely — its "disputed" occurrences are enum/constant
# declarations (VALID_PERSON_TYPES etc.), not comparisons.
_CORE_FILES = sorted(
    p for p in _CORE_DIR.glob("*.py") if p.name != "config.py"
)

# Inline marker that permanently exempts a line from the scan.
# Use only for comparisons that are semantically different from person_type checks
# (e.g. knowledge-row status columns that cannot route through _is_disputed() due
# to the circular-import boundary between core/ and pipeline.py).
_ALLOWLIST_MARKER = "disputed-row-status"

PROHIBITED_PATTERNS = [
    (r'==\s*["\']disputed["\']',                       "==  comparison"),
    (r'!=\s*["\']disputed["\']',                       "!=  comparison"),
    (r'\bis\s+["\']disputed["\']',                     "is  comparison"),
    (r'\bis\s+not\s+["\']disputed["\']',               "is not comparison"),
    (r'\bin\s*\{\s*["\']disputed["\'][,}]',            "in {...} comparison"),
    (r'\bnot\s+in\s*\{\s*["\']disputed["\'][,}]',      "not in {...} comparison"),
    (r'\bin\s*\(\s*["\']disputed["\'][,)]',            "in (...) comparison"),
    (r'\bin\s*\[\s*["\']disputed["\'][,\]]',           "in [...] comparison"),
    (r'\bcase\s+["\']disputed["\']',                   "match/case comparison"),
]


def _find_is_disputed_range(source: str) -> tuple[int, int] | None:
    """Return (start_line, end_line) 1-based of _is_disputed() via AST."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == "_is_disputed":
                return (node.lineno, node.end_lineno)
    return None


def _ast_allowlist_lines(source: str) -> set[int]:
    """Return 1-based line numbers allowlisted via AST analysis."""
    allowed: set[int] = set()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return allowed
    for node in ast.walk(tree):
        # Literal["disputed"] type annotations
        if isinstance(node, ast.Subscript):
            val = node.value
            if isinstance(val, ast.Attribute) and val.attr == "Literal":
                allowed.add(node.lineno)
            elif isinstance(val, ast.Name) and val.id == "Literal":
                allowed.add(node.lineno)
        # UPPERCASE = ... {"disputed", ...} constant assignments
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == target.id.upper():
                    allowed.add(node.lineno)
    return allowed


def _scan_source(
    source: str,
    label: str,
    *,
    exclude_range: tuple[int, int] | None = None,
    ast_allowed: set[int] | None = None,
) -> list[str]:
    """Return failure strings for prohibited patterns found in source."""
    lines = source.splitlines()
    allowed_lines: set[int] = set(ast_allowed or set())
    excluded_lines: set[int] = set()
    if exclude_range:
        start, end = exclude_range
        excluded_lines = set(range(start, end + 1))

    failures = []
    for line_no, line in enumerate(lines, 1):
        if line_no in excluded_lines:
            continue
        if line_no in allowed_lines:
            continue
        if _ALLOWLIST_MARKER in line:
            continue
        for pattern, kind in PROHIBITED_PATTERNS:
            if re.search(pattern, line):
                failures.append(
                    f"  - {kind} at {label}:{line_no}: {line.strip()!r}"
                )
                break  # one report per line is enough
    return failures


def test_no_raw_disputed_comparisons_outside_is_disputed():
    """
    P0.1 — every check for 'disputed' person_type must route through _is_disputed().

    Raw 'disputed' literal comparisons outside _is_disputed() bypass future enrichment
    of the helper (e.g. adding 'disputed_pending', 'disputed_resolved' states).
    """
    all_failures: list[str] = []

    # ── pipeline.py — exclude _is_disputed() body ──────────────────────────
    pipeline_src = _PIPELINE_PY.read_text(encoding="utf-8")
    is_disp_range = _find_is_disputed_range(pipeline_src)
    assert is_disp_range is not None, (
        "_is_disputed() not found in pipeline.py — was it renamed or deleted?"
    )
    all_failures.extend(
        _scan_source(
            pipeline_src,
            "pipeline.py",
            exclude_range=is_disp_range,
            ast_allowed=_ast_allowlist_lines(pipeline_src),
        )
    )

    # ── core/*.py — exclude core/config.py (enum declarations are fine) ────
    for core_file in _CORE_FILES:
        src = core_file.read_text(encoding="utf-8")
        all_failures.extend(
            _scan_source(
                src,
                f"core/{core_file.name}",
                ast_allowed=_ast_allowlist_lines(src),
            )
        )

    assert not all_failures, (
        "Raw 'disputed' literal comparisons found outside _is_disputed():\n"
        + "\n".join(all_failures)
        + "\n\nFix options:"
        + "\n  1. Route through _is_disputed(pid_or_session) for person_type checks."
        + "\n  2. Add # disputed-row-status comment for non-person_type domain uses."
    )
