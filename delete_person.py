"""
delete_person.py — Delete a person from every store.

Usage:
    python delete_person.py --id "jagan_abc123" --dry-run     # preview only
    python delete_person.py --id "jagan_abc123" --confirm     # actual destructive run

REQUIRES --dry-run OR --confirm. Default-deny on destructive cross-DB op
per P0.S9 D4 safety contract (highest blast radius script in repo).

Uses person_lifecycle.delete_person_everywhere() as the single authoritative
deletion path + compute_delete_preview() for the dry-run preview path.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.db import FaceDB
from core.brain_agent import BrainOrchestrator
from core.config import BRAIN_DB_PATH, GRAPH_DB_PATH, FACES_DIR
from person_lifecycle import delete_person_everywhere, compute_delete_preview

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Delete a person from every store (cross-DB destructive op)")
    parser.add_argument("--id", required=True, help="Person ID to delete")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview deletions without committing (safe; no destructive op)")
    parser.add_argument("--confirm", action="store_true",
                        help="Required for non-dry-run mode (default-deny on destructive op)")
    args = parser.parse_args()

    # P0.S9 D4 default-deny gate — destructive op requires explicit flag.
    if not args.dry_run and not args.confirm:
        print("[Delete] ERROR: destructive op requires --confirm or --dry-run",
              file=sys.stderr)
        print("        Use --dry-run first to preview; --confirm to execute.", file=sys.stderr)
        sys.exit(1)

    person_id = args.id
    faces_db = FaceDB()
    row = faces_db.get_person(person_id)
    if not row:
        print(f"[Delete] Person not found: {person_id}")
        faces_db._conn.close()
        sys.exit(1)

    person_name = row["name"]
    brain_orch = BrainOrchestrator(BRAIN_DB_PATH, GRAPH_DB_PATH)

    if args.dry_run:
        # P0.S9 D4 dry-run path — preview only; NO destructive call.
        preview = compute_delete_preview(person_id, person_name, faces_db, brain_orch)
        print(f"[Delete --dry-run] {person_name} ({person_id}) — would remove:")
        for k, v in preview.items():
            print(f"  {k}: {v}")
        faces_db._conn.close()
        brain_orch.close_connections()
        sys.exit(0)

    # Actual destructive path (--confirm gate passed).
    summary = delete_person_everywhere(person_id, person_name, faces_db, brain_orch)
    faces_db._conn.close()
    brain_orch.close_connections()

    photo = FACES_DIR / f"{person_id}.jpg"
    if photo.exists():
        photo.unlink()
        summary["photo"] = "removed"

    print(f"[Delete] {person_name} ({person_id}) — fully removed")
    for k, v in summary.items():
        print(f"  {k}: {v}")
