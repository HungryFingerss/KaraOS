"""Migrate production `assert <cond>, "<msg>"` statements to `if not <cond>: raise RuntimeError("<msg>")`.

Idempotent: re-runs report 0 modifications. Preserves error-message text verbatim.

Per Plan v2 §1.14 LOCKED 44-site scope (PI #1 absorbed; Plan v1's fabricated +4 BUG-9 cluster
expansion corrected to exact 5 sites at lines 2020/2023/2026/2029/2032):
- pipeline.py: 14 sites
- core/brain_db_migrations.py: 18 sites
- core/faces_db_migrations.py: 11 sites
- core/db.py: 1 site

Q2 RATIFIED: all migrations use `RuntimeError` uniformly (preserves exception-class invariant
for downstream try/except handlers; same observable behavior as `assert` failure under
non-`-O` mode but survives `python -O` invocation which strips asserts).
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# In-scope files for assert→raise migration (Plan v2 §1.14 LOCKED).
IN_SCOPE_FILES: tuple[str, ...] = (
    "pipeline.py",
    "core/brain_db_migrations.py",
    "core/faces_db_migrations.py",
    "core/db.py",
)


def _migrate_file(path: Path, *, check_only: bool) -> tuple[int, int]:
    """Migrate all top-level-asserts in a file. Returns (migrated_count, skipped_count)."""
    if not path.is_file():
        print(f"[ASSERT-MIGRATE] ERROR: file missing: {path}", file=sys.stderr)
        return (0, 0)
    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        print(f"[ASSERT-MIGRATE] WARN: cannot parse {path.name}: {e}", file=sys.stderr)
        return (0, 0)

    # Find all ast.Assert nodes (any nesting) with their line ranges.
    asserts: list[ast.Assert] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert):
            asserts.append(node)
    if not asserts:
        return (0, 0)

    # Sort by line number DESCENDING so we replace bottom-up (line shifts don't affect earlier lines).
    asserts.sort(key=lambda a: -a.lineno)

    lines = source.splitlines(keepends=True)
    migrated = 0
    skipped = 0

    for assert_node in asserts:
        start_line = assert_node.lineno  # 1-based, first line of assert
        end_line = assert_node.end_lineno or start_line  # 1-based, last line
        # Find indentation of the assert statement.
        first_line = lines[start_line - 1]
        indent = first_line[: len(first_line) - len(first_line.lstrip())]
        # Skip if already migrated (defensive — assert node detected means not migrated).
        # Build condition + message via ast.unparse.
        try:
            cond_src = ast.unparse(assert_node.test)
        except Exception:
            print(f"[ASSERT-MIGRATE] WARN: cannot unparse assert at {path.name}:{start_line}", file=sys.stderr)
            skipped += 1
            continue
        if assert_node.msg is not None:
            try:
                msg_src = ast.unparse(assert_node.msg)
            except Exception:
                msg_src = '"assertion failed"'
        else:
            msg_src = f'"assertion failed: {cond_src.replace(chr(34), chr(39))}"'

        # Generate replacement lines.
        new_lines = [
            f"{indent}if not ({cond_src}):\n",
            f"{indent}    raise RuntimeError({msg_src})\n",
        ]

        if check_only:
            migrated += 1
            continue

        # Replace lines[start_line-1 : end_line] with new_lines.
        lines = lines[: start_line - 1] + new_lines + lines[end_line:]
        migrated += 1

    if not check_only and migrated > 0:
        path.write_text("".join(lines), encoding="utf-8", newline="\n")

    return (migrated, skipped)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Report-only; do not modify files")
    args = parser.parse_args()

    total_migrated = 0
    total_skipped = 0
    for rel in IN_SCOPE_FILES:
        path = REPO_ROOT / rel
        m, s = _migrate_file(path, check_only=args.check)
        total_migrated += m
        total_skipped += s
        if m > 0:
            print(f"  {'WOULD-MIGRATE' if args.check else 'MIGRATED'}: {rel} ({m} sites)")
        if s > 0:
            print(f"  SKIPPED-WARN: {rel} ({s} sites with unparse errors)")

    print()
    print(f"Total migrated: {total_migrated}")
    print(f"Total skipped: {total_skipped}")
    return 0 if total_skipped == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
