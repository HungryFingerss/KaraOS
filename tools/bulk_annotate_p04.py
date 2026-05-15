"""
P0.4 Batch 0 — bulk annotate broad-silent-except sites.

ONE-SHOT script. Adds `  # TODO-P0.4: triage` to the pass line of every
unannotated broad-silent-except handler in production code.

Usage:
    python tools/bulk_annotate_p04.py [--dry-run]

Flags:
    --dry-run   Print what would change without writing files.

After running this script, `pytest tests/test_silent_except_invariant.py`
should pass (all sites annotated). The TODO-P0.4 marker is a transitional
placeholder; triage each site per the P0.4 spec:
  Bucket A — benign: replace with # CLEANUP: or # OPTIONAL:
  Bucket B — race:   replace with # RACE:
  Bucket C — silent: add logging + re-raise
  Bucket D — unknown: treat as Bucket C
"""
import ast
import sys
from pathlib import Path

# ── configuration ─────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent

SCANNED_DIRS: list[Path] = [REPO_ROOT / "core"]

SCANNED_ROOT_FILES: list[str] = [
    "pipeline.py",
    "enroll.py",
    "delete_person.py",
    "person_lifecycle.py",
    "audit_person.py",
    "repair_gallery.py",
    "sim_runner.py",
]

ALLOWLIST_PATHS: frozenset[str] = frozenset({"core/_minifasnet"})

PERMITTED_ANNOTATIONS: tuple[str, ...] = (
    "# RACE:",
    "# CLEANUP:",
    "# OPTIONAL:",
)

TODO_MARKER = "  # TODO-P0.4: triage"


# ── helpers ────────────────────────────────────────────────────────────────────

def _is_broad_except_handler(node: ast.ExceptHandler) -> bool:
    if node.type is None:
        return True
    if isinstance(node.type, ast.Name) and node.type.id in ("Exception", "BaseException"):
        return True
    if isinstance(node.type, ast.Attribute) and node.type.attr in ("Exception", "BaseException"):
        return True
    return False


def _is_silent_pass_only_body(body: list) -> bool:
    return len(body) == 1 and isinstance(body[0], ast.Pass)


def _has_annotation_comment(source: str, except_lineno: int, end_lineno: int) -> bool:
    lines = source.splitlines()
    candidate_indices = {end_lineno - 1, except_lineno - 1, except_lineno - 2}
    for idx in candidate_indices:
        if idx < 0 or idx >= len(lines):
            continue
        for ann in PERMITTED_ANNOTATIONS:
            if ann in lines[idx]:
                return True
    return False


def _is_in_allowlist(rel_str: str) -> bool:
    for allow in ALLOWLIST_PATHS:
        if rel_str == allow or rel_str.startswith(allow + "/"):
            return True
    return False


def _collect_production_files() -> list[tuple[Path, str]]:
    results: list[tuple[Path, str]] = []
    for d in SCANNED_DIRS:
        for fp in sorted(d.glob("*.py")):
            rel_str = fp.relative_to(REPO_ROOT).as_posix()
            if not _is_in_allowlist(rel_str):
                results.append((fp, rel_str))
    for name in SCANNED_ROOT_FILES:
        fp = REPO_ROOT / name
        if fp.exists():
            results.append((fp, name))
    return results


def _find_unannotated_pass_lines(file_path: Path) -> list[int]:
    """Return 1-based line numbers of pass lines that need annotation."""
    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(file_path))
    pass_lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        if not _is_broad_except_handler(node):
            continue
        if not _is_silent_pass_only_body(node.body):
            continue
        if _has_annotation_comment(source, node.lineno, node.end_lineno):
            continue
        # end_lineno is the 1-based line number of the pass statement
        pass_lines.append(node.end_lineno)
    return pass_lines


def _annotate_file(file_path: Path, pass_lines: list[int], dry_run: bool) -> int:
    """Add TODO-P0.4 comment to each pass line. Return count of lines modified."""
    source = file_path.read_text(encoding="utf-8")
    lines = source.splitlines(keepends=True)
    modified = 0
    for lineno in sorted(set(pass_lines)):
        idx = lineno - 1  # 0-based index
        if idx < 0 or idx >= len(lines):
            continue
        line = lines[idx]
        # Strip trailing newline to inspect content, then re-add
        stripped = line.rstrip("\n\r")
        if any(ann in stripped for ann in PERMITTED_ANNOTATIONS):
            continue  # already annotated (e.g. between parse and write)
        # Preserve original line ending
        ending = line[len(stripped):]
        lines[idx] = stripped + TODO_MARKER + ending
        modified += 1

    if modified > 0 and not dry_run:
        file_path.write_text("".join(lines), encoding="utf-8")

    return modified


# ── main ───────────────────────────────────────────────────────────────────────

def main(dry_run: bool = False) -> None:
    total_files = 0
    total_sites = 0

    for fp, rel_str in _collect_production_files():
        pass_lines = _find_unannotated_pass_lines(fp)
        if not pass_lines:
            continue
        count = _annotate_file(fp, pass_lines, dry_run=dry_run)
        if count:
            action = "would annotate" if dry_run else "annotated"
            print(f"  {rel_str}: {action} {count} site(s) (lines {sorted(set(pass_lines))})")
            total_files += 1
            total_sites += count

    if total_sites == 0:
        print("No unannotated broad-silent-except sites found — nothing to do.")
    else:
        mode = "[DRY RUN] " if dry_run else ""
        print(f"\n{mode}Total: {total_sites} site(s) across {total_files} file(s).")
        if dry_run:
            print("Re-run without --dry-run to apply changes.")
        else:
            print("Done. Run `pytest tests/test_silent_except_invariant.py` to verify.")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    main(dry_run=dry_run)
