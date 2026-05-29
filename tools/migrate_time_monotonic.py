"""Migrate production DEADLINE-MATH `time.time()` calls to `time.monotonic()`.

Idempotent: re-runs report 0 modifications.

Per Plan v2 §1.7 3-way taxonomy locked at Q7 ratification:
- DEADLINE-MATH (subtraction-with-stored-timestamp + while-loop guard +
  `_deadline =` assignment + comparison-to-elapsed) → migrate to `time.monotonic()`
- WALLCLOCK-WRITE → stays `time.time()` + `# WALLCLOCK:` annotation
- AMBIGUOUS → fail-safe to WALLCLOCK + annotation (preserves observability)

EXCLUDED per Plan v2 §1.13 (cross-process IPC — would break dashboard
online/offline detection if migrated to monotonic):
- `core/state.py:62` `"updated_at": time.time(),`
- `core/state.py:108` `if time.time() - data.get("updated_at", 0) > 10:`

Store getter/setter pairs migrated together: when a reader site uses
`peek_X()` and the underlying field is set via `set_X(time.time())`, BOTH the
reader and the setter caller(s) must use `time.monotonic()`.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Explicit (file, line) pairs for DEADLINE-MATH migration, locked at developer
# Pass-3 grep on 2026-05-28 per §0 NEW commitment EXTENSION dual-axis
# verification.
#
# Each entry replaces `time.time()` with `time.monotonic()` on the specified
# line. Idempotent — already-monotonic lines are skipped.
DEADLINE_MATH_SITES: tuple[tuple[str, int], ...] = (
    # === 13 explicit DEADLINE-MATH reader sites (Plan v1 §1.9 + §1.10) ===
    ("pipeline.py", 963),    # silence TTL check
    ("pipeline.py", 2773),   # _deadline = time.time() + VISION_WATCHDOG_RESTART_TIMEOUT_SECS
    ("pipeline.py", 2774),   # while time.time() < _deadline
    ("pipeline.py", 2915),   # GREET_COOLDOWN check
    ("pipeline.py", 3313),   # cloud-state elapsed
    ("pipeline.py", 3396),   # face-in-frame staleness
    ("pipeline.py", 5636),   # YOLO throttle
    ("pipeline.py", 5758),   # cloud-flap elapsed
    ("pipeline.py", 7454),   # face-loss grace_expired
    ("pipeline.py", 7753),   # face-loss grace_expired (second site)
    ("pipeline.py", 8419),   # presence recognized elapsed
    ("pipeline.py", 8457),   # face-in-frame staleness (second site)
    ("core/brain_agent.py", 6908),  # Kuzu rebuild_secs duration

    # === Store setter writer sites (paired with the above readers) ===
    ("pipeline.py", 967),    # set_last_silent_update(time.time()) — paired with 963 reader
    ("pipeline.py", 2813),   # set_vision_heartbeat(time.time())
    ("pipeline.py", 2833),   # set_last_face_seen(time.time())
    ("pipeline.py", 2835),   # set_last_face_seen(time.time())
    ("pipeline.py", 3492),   # set_last_kairos_at(time.time())
    ("pipeline.py", 3494),   # set_last_kairos_at(time.time())
    ("pipeline.py", 3536),   # set_last_kairos_at(time.time())
    ("pipeline.py", 3538),   # set_last_kairos_at(time.time())
    ("pipeline.py", 6715),   # set_last_user_speech_at(time.time())
    ("pipeline.py", 6716),   # set_last_kairos_at(time.time())
    ("pipeline.py", 7475),   # _now_face = time.time() — feeds 7480/7490 setters
    ("pipeline.py", 7666),   # set_last_user_speech_at(time.time())
    ("pipeline.py", 7721),   # set_last_user_speech_at(time.time())
    ("pipeline.py", 7765),   # set_last_user_speech_at(time.time())

    # === Compare-with-subtraction DEADLINE pattern in other files ===
    ("core/cache_store.py", 87),  # if (time.time() - ts) >= self._ttl  — CacheStore TTL gate

    # === Developer Pass-3 grep at Phase 4 refinement (+6 sites beyond Plan v2 §1.8 ~28 estimate) ===
    # Banked at closure narrative as `Plan-v1-Pass-2-grep-undercount` 14 → 15 instance.
    ("pipeline.py", 548),    # return (time.time() - last_seen) < SCENE_STALE_SECS  — scene staleness
    ("pipeline.py", 601),    # time.time() - started_at > ENROLLMENT_RENAME_GRACE_SECS  — enrollment-mishear gate
    ("pipeline.py", 7230),   # time.time() - last >= SELF_UPDATE_COOLDOWN  — self-update cool-down
    ("pipeline.py", 7259),   # time.time() - last_greeted >= GREET_COOLDOWN  — greet cool-down (2nd site)
    ("pipeline.py", 7390),   # time.time() - last_seen_ts >= BRIEFING_MIN_ABSENCE  — briefing absence gate
    ("pipeline.py", 7458),   # time.time() - last_sighted >= GREET_COOLDOWN  — sight-based cool-down
)

# Explicit (file, line, reason) for sites needing `# WALLCLOCK:` annotation.
# These STAY as `time.time()` because they're WALLCLOCK-semantic; the annotation
# documents intent + is the allowlist key for the D2 AST invariant detector.
WALLCLOCK_ANNOTATION_SITES: tuple[tuple[str, int, str], ...] = (
    # cross-process IPC — pipeline writes, dashboard reads via JSON state file
    ("core/state.py", 62, "cross-process IPC"),
    ("core/state.py", 108, "cross-process IPC"),

    # WALLCLOCK-WRITE: nudge expiry stored in DB → must be wallclock semantic (survives restart;
    # later compared to wallclock now in other paths). Migrating would break DB-stored deadlines.
    ("core/brain_agent.py", 6155, "nudge expiry stored persistently in DB"),

    # WALLCLOCK-WRITE: visitor alert nudge expires_at stored persistently — same DB-stored semantic.
    ("core/brain_agent.py", 7423, "visitor alert expires_at stored persistently in DB"),

    # WALLCLOCK-READ: factory_reset CLI checks pipeline-live via state.json::updated_at heuristic.
    # Same cross-process IPC semantic as core/state.py:108.
    ("tools/factory_reset.py", 67, "cross-process IPC (state.json updated_at)"),
)


def migrate_line(path: Path, line_num: int, *, check_only: bool) -> str:
    """Replace `time.time()` with `time.monotonic()` on the specified line.
    Returns 'migrated' / 'skipped' (already monotonic) / 'error' / 'unchanged' (no time.time()).
    """
    if not path.is_file():
        print(f"[MIGRATE] ERROR: file missing: {path}", file=sys.stderr)
        return "error"
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    if line_num > len(lines):
        print(f"[MIGRATE] ERROR: line {line_num} out of range in {path.name}", file=sys.stderr)
        return "error"
    src = lines[line_num - 1]
    if "time.monotonic()" in src and "time.time()" not in src:
        return "skipped"
    if "time.time()" not in src:
        return "unchanged"
    if check_only:
        return "migrated"
    # Replace time.time() with time.monotonic() on this line only.
    new_src = src.replace("time.time()", "time.monotonic()")
    lines[line_num - 1] = new_src
    path.write_text("".join(lines), encoding="utf-8", newline="\n")
    return "migrated"


def annotate_line(path: Path, line_num: int, reason: str, *, check_only: bool) -> str:
    """Insert a `# WALLCLOCK: <reason>` comment above the FIRST `time.time()` line
    at-or-after `line_num` (window: line_num to line_num+10) if no annotation present
    in the 3-line window above that site.

    Robust against line-number drift after a previous run shifted the target line
    by inserting earlier annotations: the lookup re-finds the time.time() call
    rather than blindly trusting the line number.

    Returns 'annotated' / 'skipped' (already annotated) / 'error'.
    """
    if not path.is_file():
        return "error"
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    annotation = f"# WALLCLOCK: {reason}"
    # Re-locate the time.time() line within [line_num - 5, line_num + 10] window.
    window_start = max(0, line_num - 6)
    window_end = min(len(lines), line_num + 10)
    target_idx = None
    for i in range(window_start, window_end):
        if "time.time()" in lines[i]:
            target_idx = i
            break
    if target_idx is None:
        return "error"
    # Check if any WALLCLOCK annotation exists in the 3 lines above the target.
    for j in range(max(0, target_idx - 3), target_idx):
        if "# WALLCLOCK:" in lines[j]:
            return "skipped"
    # Check inline on target line too.
    if "# WALLCLOCK:" in lines[target_idx]:
        return "skipped"
    if check_only:
        return "annotated"
    # Insert annotation immediately above target line with matching indentation.
    indent_match = re.match(r"^(\s*)", lines[target_idx])
    indent = indent_match.group(1) if indent_match else ""
    new_lines = lines[:target_idx] + [f"{indent}{annotation}\n"] + lines[target_idx:]
    path.write_text("".join(new_lines), encoding="utf-8", newline="\n")
    return "annotated"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Report-only; do not modify files")
    args = parser.parse_args()

    print("=== DEADLINE-MATH migration sites ===")
    migrate_stats = {"migrated": 0, "skipped": 0, "error": 0, "unchanged": 0}
    # Process sites in reverse line order so line-number shifts from annotations don't affect later migrations.
    # (Migration doesn't shift line numbers; annotation does. We do migrations first, then annotations.)
    seen_sites: set[tuple[str, int]] = set()
    for rel, line_num in DEADLINE_MATH_SITES:
        if (rel, line_num) in seen_sites:
            continue
        seen_sites.add((rel, line_num))
        path = REPO_ROOT / rel
        result = migrate_line(path, line_num, check_only=args.check)
        migrate_stats[result] = migrate_stats.get(result, 0) + 1
        if result == "migrated":
            print(f"  {'WOULD-MIGRATE' if args.check else 'MIGRATED'}: {rel}:{line_num}")
        elif result == "skipped":
            print(f"  SKIPPED (already monotonic): {rel}:{line_num}")
        elif result == "error":
            print(f"  ERROR: {rel}:{line_num}")
        elif result == "unchanged":
            print(f"  UNCHANGED (no time.time on line): {rel}:{line_num}")

    print()
    print("=== WALLCLOCK annotation sites ===")
    annotate_stats = {"annotated": 0, "skipped": 0, "error": 0}
    # Process annotations in REVERSE line order — inserting a line shifts subsequent lines down.
    for rel, line_num, reason in sorted(WALLCLOCK_ANNOTATION_SITES, key=lambda x: -x[1]):
        path = REPO_ROOT / rel
        result = annotate_line(path, line_num, reason, check_only=args.check)
        annotate_stats[result] = annotate_stats.get(result, 0) + 1
        if result == "annotated":
            print(f"  {'WOULD-ANNOTATE' if args.check else 'ANNOTATED'}: {rel}:{line_num} ({reason})")
        elif result == "skipped":
            print(f"  SKIPPED (already annotated): {rel}:{line_num}")

    print()
    print(f"Migrated: {migrate_stats['migrated']}")
    print(f"Skipped: {migrate_stats['skipped']}")
    print(f"Errors: {migrate_stats['error']}")
    print(f"Unchanged: {migrate_stats['unchanged']}")
    print(f"Annotated: {annotate_stats['annotated']}")
    print(f"Annotation skipped: {annotate_stats['skipped']}")

    return 0 if migrate_stats["error"] == 0 and annotate_stats["error"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
