"""Apply SPDX-License-Identifier + SPDX-FileCopyrightText headers to KaraOS sources.

Idempotent: re-runs report 0 modifications. Excludes vendored MIT-licensed paths
per PI #3 (Plan v3 absorption 2026-05-28). Vendored MIT compliance handled at
directory level by Bundle 2.X (`core/_minifasnet/LICENSE`).

SPDX scope (202 files locked at Plan v3 §1.2):
- `core/**/*.py` excluding `core/_minifasnet/` ... 47 files
- Top-level entry points (4): pipeline.py + enroll.py + delete_person.py + audit_person.py
- `tools/*.py` ........................................ 6 files
- `bootstrap/classifier/**/*.py` ....................... 10 files
- `tests/**/*.py` ..................................... 131 files
- `.github/workflows/*.yml` ............................ 4 files

Per REUSE Software spec semantics, SPDX-License-Identifier declares the file's
actual license. Uniform Apache-2.0 application to MIT-licensed vendored code
would either misrepresent the license, assert unauthorized sublicensing, or
create ambiguous declaration. Hence EXCLUDED_PATHS.

Also performs idempotent `.gitignore` whitelist update for the 3 new governance
markdown files (`!/GOVERNANCE.md`, `!/CODE_OF_CONDUCT.md`, `!/CONTRIBUTING.md`).

Usage:
    python tools/add_spdx_headers.py        # apply
    python tools/add_spdx_headers.py --check # report-only; non-zero exit on missing
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import argparse
import ast
import pathlib
import sys
import traceback

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

EXCLUDED_PATHS: tuple[str, ...] = ("core/_minifasnet/",)  # PI #3 absorption

SPDX_LICENSE_LINE = "# SPDX-License-Identifier: Apache-2.0"
SPDX_COPYRIGHT_LINE = "# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors"
HEADER_PYTHON = f"{SPDX_LICENSE_LINE}\n{SPDX_COPYRIGHT_LINE}\n"
HEADER_YAML = f"{SPDX_LICENSE_LINE}\n{SPDX_COPYRIGHT_LINE}\n"

GITIGNORE_WHITELIST_LINES: tuple[str, ...] = (
    "!/GOVERNANCE.md",
    "!/CODE_OF_CONDUCT.md",
    "!/CONTRIBUTING.md",
)


def collect_in_scope() -> list[pathlib.Path]:
    """Return the locked 202-file in-scope list per Plan v3 §1.2."""
    files: list[pathlib.Path] = []

    # core/ excluding _minifasnet/
    for p in sorted((REPO_ROOT / "core").rglob("*.py")):
        if "_minifasnet" not in p.parts:
            files.append(p)

    # Top-level entry points
    for name in ("pipeline.py", "enroll.py", "delete_person.py", "audit_person.py"):
        p = REPO_ROOT / name
        if p.is_file():
            files.append(p)

    # tools/*.py (top-level only)
    files.extend(sorted(p for p in (REPO_ROOT / "tools").glob("*.py") if p.is_file()))

    # bootstrap/classifier/**/*.py
    boot = REPO_ROOT / "bootstrap" / "classifier"
    if boot.exists():
        files.extend(sorted(boot.rglob("*.py")))

    # tests/**/*.py
    files.extend(sorted((REPO_ROOT / "tests").rglob("*.py")))

    # .github/workflows/*.yml
    files.extend(sorted((REPO_ROOT / ".github" / "workflows").glob("*.yml")))

    return files


def is_excluded(path: pathlib.Path) -> bool:
    rel = path.relative_to(REPO_ROOT).as_posix()
    return any(rel.startswith(prefix) for prefix in EXCLUDED_PATHS)


def collect_excluded() -> list[pathlib.Path]:
    """Return files that match EXCLUDED_PATHS prefixes within the broader source tree."""
    excluded: list[pathlib.Path] = []
    for p in sorted((REPO_ROOT / "core").rglob("*.py")):
        if is_excluded(p):
            excluded.append(p)
    return excluded


def has_spdx_header(content: str, *, is_python: bool) -> bool:
    """True if SPDX header lines present at the canonical insertion position.

    For Python: check the lines immediately after the module docstring's
    closing triple-quote (or the first 10 lines if no docstring). Long
    docstrings push the header position beyond a fixed line-window, so the
    AST-derived position is the only reliable probe.

    For YAML: check the first 10 lines (no docstring convention).

    A line-start `# SPDX-License-Identifier: ...` AND `# SPDX-FileCopyrightText: ...`
    pair within the search window means the file is already headered.
    """
    all_lines = content.split("\n")
    if is_python:
        docstring_end = find_python_docstring_end(content)
        if docstring_end is None:
            search_window = all_lines[:10]
        else:
            search_window = all_lines[docstring_end:docstring_end + 10]
    else:
        search_window = all_lines[:10]
    has_license = any(line.lstrip().startswith(SPDX_LICENSE_LINE) for line in search_window)
    has_copyright = any(line.lstrip().startswith(SPDX_COPYRIGHT_LINE) for line in search_window)
    return has_license and has_copyright


def find_python_docstring_end(content: str) -> int | None:
    """Return 0-based line index AFTER the module docstring (closing triple-quote), or None."""
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return None
    if not tree.body:
        return None
    first = tree.body[0]
    if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
        end_line = first.value.end_lineno
        if end_line is None:
            return None
        return end_line  # 1-based last line of docstring → 0-based insertion point is end_line
    return None


def insert_python_header(content: str) -> str:
    """Insert HEADER_PYTHON after module docstring; line 1 if no docstring; return new content."""
    lines = content.split("\n")
    docstring_end = find_python_docstring_end(content)

    if docstring_end is not None:
        # Insert after docstring + ensure there's a blank line between docstring and header.
        insert_at = docstring_end  # 0-based index of first line AFTER docstring
        # Skip past any blank lines that already follow the docstring.
        while insert_at < len(lines) and lines[insert_at].strip() == "":
            insert_at += 1
        # Inject: blank-line + 2 SPDX lines + blank-line, normalized.
        new_lines = (
            lines[:docstring_end]
            + [""]
            + [SPDX_LICENSE_LINE, SPDX_COPYRIGHT_LINE]
            + [""]
            + lines[insert_at:]
        )
    else:
        # No module docstring → header at line 1 (after shebang if present).
        if lines and lines[0].startswith("#!"):
            new_lines = [lines[0], SPDX_LICENSE_LINE, SPDX_COPYRIGHT_LINE, ""] + lines[1:]
        else:
            new_lines = [SPDX_LICENSE_LINE, SPDX_COPYRIGHT_LINE, ""] + lines

    return "\n".join(new_lines)


def insert_yaml_header(content: str) -> str:
    """Insert HEADER_YAML at line 1 (after shebang if present)."""
    lines = content.split("\n")
    if lines and lines[0].startswith("#!"):
        new_lines = [lines[0], SPDX_LICENSE_LINE, SPDX_COPYRIGHT_LINE, ""] + lines[1:]
    else:
        new_lines = [SPDX_LICENSE_LINE, SPDX_COPYRIGHT_LINE, ""] + lines
    return "\n".join(new_lines)


def update_gitignore() -> int:
    """Add 3 whitelist negations to .gitignore if absent. Returns count of lines added."""
    gitignore = REPO_ROOT / ".gitignore"
    content = gitignore.read_text(encoding="utf-8")
    missing = [line for line in GITIGNORE_WHITELIST_LINES if line not in content]
    if not missing:
        return 0
    # Append at end of file with explanatory comment block.
    if not content.endswith("\n"):
        content += "\n"
    addition = "\n# Governance docs (Pre-P1 Bundle 2 2026-05-28) — whitelist past the /*.md rule.\n"
    addition += "\n".join(missing) + "\n"
    gitignore.write_text(content + addition, encoding="utf-8", newline="\n")
    return len(missing)


def process_file(path: pathlib.Path, *, check_only: bool) -> str:
    """Apply SPDX header. Return 'added' / 'skipped' / 'excluded' / 'error'."""
    rel = path.relative_to(REPO_ROOT).as_posix()
    if is_excluded(path):
        return "excluded"
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        print(f"[SPDX] WARN ({type(e).__name__}): cannot read {rel}: {e}", file=sys.stderr)
        return "error"
    is_python = path.suffix == ".py"
    if has_spdx_header(content, is_python=is_python):
        return "skipped"
    if check_only:
        return "added"  # would-be-added
    try:
        if path.suffix == ".py":
            new_content = insert_python_header(content)
        elif path.suffix == ".yml":
            new_content = insert_yaml_header(content)
        else:
            print(f"[SPDX] WARN: unknown extension for {rel}", file=sys.stderr)
            return "error"
        path.write_text(new_content, encoding="utf-8", newline="\n")
        return "added"
    except Exception as e:
        print(f"[SPDX] WARN ({type(e).__name__}): cannot write {rel}: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return "error"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Report-only; do not modify files")
    args = parser.parse_args()

    in_scope = collect_in_scope()
    excluded_files = collect_excluded()

    stats = {"added": 0, "skipped": 0, "excluded": 0, "error": 0}

    for path in in_scope:
        result = process_file(path, check_only=args.check)
        stats[result] += 1
        if result == "excluded":
            print(f"[SPDX] EXCLUDED (vendored MIT): {path.relative_to(REPO_ROOT).as_posix()}")
        elif result == "added" and not args.check:
            print(f"[SPDX] {'WOULD-ADD' if args.check else 'ADDED'}: {path.relative_to(REPO_ROOT).as_posix()}")

    # Tally encountered excluded files matched by EXCLUDED_PATHS even if not in in-scope list.
    # PI #3 invariant: EXCLUDED count must equal 2 (the core/_minifasnet/ files).
    excluded_count = len(excluded_files)
    stats["excluded"] = excluded_count

    if not args.check:
        gitignore_added = update_gitignore()
    else:
        gitignore = REPO_ROOT / ".gitignore"
        content = gitignore.read_text(encoding="utf-8")
        gitignore_added = sum(1 for line in GITIGNORE_WHITELIST_LINES if line not in content)

    print()
    print(f"In-scope files: {len(in_scope)}")
    print(f"Added: {stats['added']}")
    print(f"Skipped: {stats['skipped']}")
    print(f"Excluded: {excluded_count}")
    print(f"Errors: {stats['error']}")
    print(f".gitignore lines added: {gitignore_added}")

    return 1 if (args.check and (stats["added"] > 0 or gitignore_added > 0)) else 0


if __name__ == "__main__":
    sys.exit(main())
