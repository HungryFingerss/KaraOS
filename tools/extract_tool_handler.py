"""P0.8 handler extraction helper.

Pure mechanical extraction: lifts the body of `if name == "<tool>":` (or
`elif name == "<tool>":`) out of `_execute_tool` and into a new async
top-level function `_handle_<tool>(args, ctx)`.  Replaces the original
branch body with a single delegation line.

Discipline guardrails (P0.8 reviewer spec):
- Verbatim move.  No cleanup, no signature improvement, no comment edits.
- Local names re-bound from ctx at the top of the handler so the body
  reads identically to the original branch.
- Idempotent: re-running on an already-extracted handler is a no-op.

Usage:
    python tools/extract_tool_handler.py <tool_name>

Example:
    python tools/extract_tool_handler.py update_person_name
"""
from __future__ import annotations

import pathlib
import re
import sys
import textwrap

REPO = pathlib.Path(__file__).resolve().parent.parent
PIPELINE = REPO / "pipeline.py"


# Local-name unpack block prepended to each handler body so closures match
# the original branch verbatim.  Order matches _ToolContext field order.
_UNPACK_HEADER = textwrap.dedent('''
    # P0.8 mechanical extraction (handler body is verbatim from the original
    # _execute_tool branch).  Local names rebind from ctx so the body reads
    # identically.  Intent + grounding gates stay inside — P1.A3 extracts
    # them next.
    args           = ctx.args
    person_id      = ctx.person_id
    person_name    = ctx.person_name
    db             = ctx.db
    user_text      = ctx.user_text
    intent_sidecar = ctx.intent_sidecar
    _exec_snap     = ctx.exec_snap
''').strip("\n")


def find_branch_span(lines: list[str], tool_name: str) -> tuple[int, int]:
    """Return (start_idx, end_idx_exclusive) of the branch body lines for
    `if/elif name == "<tool>":`.  Body starts AFTER the if/elif line and
    ends at the line BEFORE the next `elif name ==` or before the dedent
    that closes _execute_tool.
    """
    header_pat = re.compile(
        r'^\s{4}(?:if|elif)\s+name\s*==\s*"'
        + re.escape(tool_name)
        + r'":\s*$'
    )
    start = None
    for i, ln in enumerate(lines):
        if header_pat.match(ln):
            start = i + 1
            break
    if start is None:
        raise SystemExit(f"branch for tool '{tool_name}' not found")

    # End of branch: next `    elif name ==` line OR a dedent (line with
    # exactly 4 spaces or fewer that is not part of the body).  In
    # _execute_tool the body uses 8-space indent; siblings use 4-space.
    end = None
    next_branch_pat = re.compile(r'^\s{4}elif\s+name\s*==\s*"')
    function_end_pat = re.compile(r'^\S')  # line that starts at column 0
    for i in range(start, len(lines)):
        ln = lines[i]
        if next_branch_pat.match(ln):
            end = i
            break
        if function_end_pat.match(ln):
            end = i
            break
        # Sibling statement at the _execute_tool level (4-space indent, NOT
        # blank, NOT inside the branch): closes the branch.
        if (ln.startswith("    ") and not ln.startswith("     ")
                and ln.strip() and not ln.startswith("    #")):
            # Strict 4-space — but stripped non-blank.  This catches the
            # trailing `return None` at L4350 outside the if/elif chain.
            end = i
            break
    if end is None:
        raise SystemExit(f"end of branch '{tool_name}' not found")
    # Trim trailing blank lines from the body (keep them after the
    # delegation in the rewritten function).
    while end > start and lines[end - 1].strip() == "":
        end -= 1
    return start, end


def already_extracted(src: str, tool_name: str) -> bool:
    return re.search(
        rf'^async\s+def\s+_handle_{re.escape(tool_name)}\s*\(',
        src,
        re.MULTILINE,
    ) is not None


def build_handler(tool_name: str, body_lines: list[str]) -> str:
    """Construct the new top-level `async def _handle_<tool>` function."""
    dedented = textwrap.dedent("".join(body_lines))
    # Indent unpack header + body uniformly at 4 spaces (function-body level).
    parts = [
        f"async def _handle_{tool_name}(args: dict, ctx: \"_ToolContext\") -> \"str | None\":",
        f'    """P0.8 extracted handler — verbatim move of {tool_name} branch from _execute_tool."""',
    ]
    for ln in _UNPACK_HEADER.splitlines():
        parts.append(f"    {ln}" if ln.strip() else "")
    parts.append("")  # blank line between header and body
    for ln in dedented.splitlines():
        parts.append(f"    {ln}" if ln.strip() else "")
    return "\n".join(parts) + "\n\n\n"


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    tool = sys.argv[1]

    src = PIPELINE.read_text(encoding="utf-8")
    if already_extracted(src, tool):
        print(f"[extract] _handle_{tool} already present — no-op")
        return
    lines = src.splitlines(keepends=True)

    start, end = find_branch_span(lines, tool)
    body = lines[start:end]
    if not body:
        raise SystemExit(f"empty body for tool '{tool}'")

    handler_text = build_handler(tool, body)

    # Insert handler ABOVE `async def _execute_tool(`.
    exec_anchor_pat = re.compile(r'^async\s+def\s+_execute_tool\s*\(', re.MULTILINE)
    m = exec_anchor_pat.search(src)
    if not m:
        raise SystemExit("could not locate `async def _execute_tool(`")
    insert_at = m.start()
    new_src = src[:insert_at] + handler_text + src[insert_at:]

    # Build the delegation replacement.  body[0] is the first line of the
    # branch body (8-space indent).  Replace [start:end] with a 2-line
    # delegation at 8-space indent.
    delegation = (
        "        return await _handle_{tool}(args, _ctx)\n".format(tool=tool)
    )

    # Re-tokenize new_src — its line offsets shifted by the handler insert.
    # Easier: re-run the branch search on new_src.
    lines2 = new_src.splitlines(keepends=True)
    start2, end2 = find_branch_span(lines2, tool)
    new_lines = lines2[:start2] + [delegation] + lines2[end2:]
    PIPELINE.write_text("".join(new_lines), encoding="utf-8")
    print(f"[extract] _handle_{tool} added; branch body collapsed to delegation")


if __name__ == "__main__":
    main()
