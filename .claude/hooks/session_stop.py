"""
session_stop.py — Runs after every Claude response (Stop event).
Lightweight: just stamps the log so we know when the last interaction was.
Heavy context-saving is done by Claude updating CLAUDE.md during the session.
"""
import sys
from datetime import datetime
from pathlib import Path

LOG_FILE = Path(__file__).parent / "session.log"


def main():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{now}] STOP (last response)\n")


if __name__ == "__main__":
    main()
