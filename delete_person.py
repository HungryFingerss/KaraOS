"""
delete_person.py — Delete a person from every store.
Called by: python delete_person.py --id "jagan_abc123"
Uses person_lifecycle.delete_person_everywhere() as the single authoritative deletion path.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.db import FaceDB
from core.brain_agent import BrainOrchestrator
from core.config import BRAIN_DB_PATH, GRAPH_DB_PATH, FACES_DIR
from person_lifecycle import delete_person_everywhere

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", required=True, help="Person ID to delete")
    args = parser.parse_args()

    person_id = args.id

    faces_db = FaceDB()
    row = faces_db.get_person(person_id)
    if not row:
        print(f"[Delete] Person not found: {person_id}")
        faces_db._conn.close()
        sys.exit(1)

    person_name = row["name"]
    brain_orch = BrainOrchestrator(BRAIN_DB_PATH, GRAPH_DB_PATH)

    summary = delete_person_everywhere(person_id, person_name, faces_db, brain_orch)

    faces_db._conn.close()
    brain_orch.close_connections()

    # Delete photo if present
    photo = FACES_DIR / f"{person_id}.jpg"
    if photo.exists():
        photo.unlink()
        summary["photo"] = "removed"

    print(f"[Delete] {person_name} ({person_id}) — fully removed")
    for k, v in summary.items():
        print(f"  {k}: {v}")
