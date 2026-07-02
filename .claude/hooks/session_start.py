"""
session_start.py — Runs when Claude Code opens this project.
Prints a context banner so Claude immediately knows where things stand.
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT      = Path(__file__).parent.parent.parent   # repo root
LOG_FILE  = Path(__file__).parent / "session.log"
STATE_DIR = Path(__file__).parent                 # .claude/


def _last_session_summary() -> str:
    if not LOG_FILE.exists():
        return "  (no previous session log found)"
    lines = LOG_FILE.read_text(encoding="utf-8").strip().splitlines()
    # Return last 5 lines of the log for context
    recent = lines[-5:] if len(lines) >= 5 else lines
    return "\n".join(f"  {l}" for l in recent)


def _test_count() -> str:
    """Read the test count from CLAUDE.md header line."""
    claude_md = ROOT / "CLAUDE.md"
    if not claude_md.exists():
        return "unknown"
    for line in claude_md.read_text(encoding="utf-8").splitlines()[:5]:
        if "Tests:" in line:
            return line.split("Tests:")[-1].strip()
    return "unknown"


def main():
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    print("=" * 60)
    print("  KARAOS SESSION STARTED")
    print(f"  {now}")
    print(f"  Tests: {_test_count()}")
    print()
    print("  Recent session log:")
    print(_last_session_summary())
    print("=" * 60)
    print()
    print("  CLAUDE.md loaded — project context is available.")
    print("  Run: pytest test_faiss_delete.py test_vision_v1v4.py")
    print("             test_executor.py test_shutdown.py -v")
    print("  to confirm green state before starting work.")
    print("=" * 60)

    # Append session-start to log
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{now}] SESSION START\n")


if __name__ == "__main__":
    main()
