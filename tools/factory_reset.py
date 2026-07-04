"""Standalone factory reset CLI — wipes faces.db / brain.db / FAISS / Kuzu / photos.

Preserves `.dashboard_token` and `.dashboard_auth_url` per P0.S2 invariant
(re-issuing auth URL on every reset is hostile UX; token is single-user-
scoped — no cross-tenant risk). Use --include-dashboard-token to override.

P0.S11 Plan v1 §2 D1 — addresses the 2026-05-27 canary day-1 diagnostic gap
where the user thought a factory reset had been performed but in fact only
`.dashboard_token` was removed; faces.db + brain.db + voice gallery survived.

Safety:
  - DEFAULT MODE = DRY RUN. Lists what WOULD be deleted; takes no destructive
    action. Requires explicit --confirm flag to actually delete.
  - PIPELINE-LIVENESS CHECK. Refuses to run if pipeline is currently active
    (Windows file-locks would make wipe_all() partially fail with cryptic
    PermissionError 32 messages). Polls faces/state.json::updated_at — if
    last update was within 10s, considers pipeline live.
  - .dashboard_token PRESERVED by default per P0.S2 invariant. Use
    --include-dashboard-token to delete it too (e.g. full re-init scenarios
    where dashboard auth needs re-issuance).

Usage:

    python tools/factory_reset.py                              # dry-run (default)
    python tools/factory_reset.py --confirm                    # actually wipe
    python tools/factory_reset.py --confirm --include-dashboard-token
    python tools/factory_reset.py --confirm --force            # bypass pipeline-liveness check (use ONLY when pipeline known stopped)

Exit codes:
    0   Success (dry-run completed OR wipe completed cleanly)
    1   Pipeline is live and --force not specified
    2   wipe_all() raised an exception
    3   --include-dashboard-token specified but token files couldn't be deleted

Spec: rule book/cycle-specs/p0_s11_factory_reset_cli_plan_v1.md
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core.db import wipe_all, FACES_DIR, DB_PATH, BRAIN_DB_PATH, FAISS_INDEX_PATH, GRAPH_DB_PATH


def _is_pipeline_live() -> bool:
    """Mirror of dashboard's isPipelineLive() heuristic — read faces/state.json,
    check if updated_at is within last 10 seconds. False on missing file or
    parse error (safer to assume offline + let wipe_all proceed than to
    refuse-and-leave-stuck)."""
    import json
    state_path = FACES_DIR / "state.json"
    if not state_path.exists():
        return False
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        updated_at = float(data.get("updated_at", 0))
        # WALLCLOCK: cross-process IPC (state.json updated_at)
        return (time.time() - updated_at) < 10.0
    except (json.JSONDecodeError, OSError, ValueError):
        return False


def _enumerate_targets(include_dashboard_token: bool) -> tuple[list[str], list[str]]:
    """Return (to_delete, to_preserve) lists for dry-run + summary purposes.
    Order matches wipe_all() body for grep-correspondence."""
    targets = [
        str(DB_PATH) + s for s in ("", "-shm", "-wal")
    ] + [
        str(FAISS_INDEX_PATH),
    ] + [
        str(BRAIN_DB_PATH) + s for s in ("", "-shm", "-wal")
    ] + [
        str(GRAPH_DB_PATH),
        str(GRAPH_DB_PATH) + ".wal",
        str(GRAPH_DB_PATH) + "-lock",
    ] + [
        str(p) for p in FACES_DIR.glob("*.jpg")
    ] + [
        str(FACES_DIR / "enroll_request.json"),
        str(FACES_DIR / "enroll_result.json"),
        str(FACES_DIR / "reset_request.json"),
        str(FACES_DIR / "reset_result.json"),
        str(FACES_DIR.parent / "sim_session_state.json"),
    ]
    preserved = [
        str(FACES_DIR / ".dashboard_token"),
        str(FACES_DIR / ".dashboard_auth_url"),
    ]
    if include_dashboard_token:
        targets.extend(preserved)
        preserved = []
    return targets, preserved


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Standalone factory reset for KaraOS (wipes faces.db / brain.db / FAISS / Kuzu / photos)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--confirm", action="store_true",
                        help="Actually perform the wipe (default: dry-run)")
    parser.add_argument("--include-dashboard-token", action="store_true",
                        help="Also delete .dashboard_token and .dashboard_auth_url (default: preserved per P0.S2)")
    parser.add_argument("--force", action="store_true",
                        help="Bypass pipeline-liveness check (use only when pipeline known stopped)")
    args = parser.parse_args()

    # Pipeline-liveness check (D1.A4)
    if not args.force and _is_pipeline_live():
        print(
            "[Reset] ERROR: Pipeline appears to be running "
            "(faces/state.json::updated_at within last 10s).\n"
            "Stop the pipeline first OR use the dashboard's /api/factory-reset endpoint\n"
            "(which sends IPC to the running pipeline). Override with --force ONLY if you\n"
            "are certain the pipeline is stopped.",
            file=sys.stderr,
        )
        return 1

    targets, preserved = _enumerate_targets(args.include_dashboard_token)

    # Dry-run mode (D1.A2 — default-deny safety gate)
    if not args.confirm:
        print("[Reset] DRY RUN — no files will be deleted.")
        print(f"[Reset] Would delete {len(targets)} target(s):")
        for t in targets:
            exists = "  \u2713" if Path(t).exists() else "  \u00b7"  # ✓ = exists, · = absent
            print(f"  {exists} {t}")
        print(f"[Reset] Would preserve {len(preserved)} target(s):")
        for p in preserved:
            exists = "  \u2713" if Path(p).exists() else "  \u00b7"
            print(f"  {exists} {p}")
        print("[Reset] To actually wipe, re-run with --confirm.")
        return 0

    # Real wipe (D1.A1 + D1.A3)
    print(f"[Reset] CONFIRMED — wiping {len(targets)} target(s) (preserving {len(preserved)})...")
    try:
        wipe_all()
        # D1.A3 — if --include-dashboard-token, ALSO delete the preserved files
        # (wipe_all preserves them per P0.S2; CLI's job is to override that
        # when the user explicitly asks for it)
        if args.include_dashboard_token:
            for p in [FACES_DIR / ".dashboard_token", FACES_DIR / ".dashboard_auth_url"]:
                try:
                    p.unlink(missing_ok=True)
                    print(f"[Reset] Deleted {p.name} (--include-dashboard-token)")
                except Exception as e:
                    print(f"[Reset] WARN: could not delete {p.name}: {e}", file=sys.stderr)
                    return 3
    except Exception as e:
        print(f"[Reset] ERROR: wipe_all() raised: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
