"""
audit_person.py — Inspect and optionally repair a person's face gallery.

Usage:
  python audit_person.py --id <person_id>              # show outlier analysis
  python audit_person.py --id <person_id> --repair     # delete outliers + rebuild FAISS
  python audit_person.py --all                         # audit every enrolled person
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.db import FaceDB
from core.audit import audit_gallery, repair_gallery


def _print_result(r: dict, *, repair_count: int | None = None) -> None:
    pid = r["person_id"]
    total = r["total"]
    outliers = r.get("outliers", [])
    note = r.get("note", "")

    status = "OK" if not outliers else f"{len(outliers)} OUTLIER(S)"
    print(f"\n[Audit] {pid} — {total} embedding(s) — {status}")
    if note:
        print(f"  Note: {note}")
    else:
        print(f"  mean_dist={r['mean_distance']:.4f}  std={r['std_distance']:.4f}  threshold={r.get('threshold', 0):.4f}")

    for o in outliers:
        import datetime
        ts = datetime.datetime.fromtimestamp(o["captured_at"]).strftime("%Y-%m-%d %H:%M")
        print(
            f"  OUTLIER row_id={o['row_id']} source={o['source']!r} "
            f"conf={o['confidence_at_write']:.2f} dist={o['distance_from_centroid']:.4f} ts={ts}"
        )

    if repair_count is not None:
        print(f"  → Removed {repair_count} outlier row(s) and rebuilt FAISS index.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Audit face gallery for outlier embeddings")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--id", help="Person ID to audit")
    group.add_argument("--all", action="store_true", help="Audit all enrolled persons")
    parser.add_argument("--repair", action="store_true", help="Delete outliers and rebuild FAISS")
    parser.add_argument("--json", action="store_true", help="Output JSON (for scripts/dashboard)")
    args = parser.parse_args()

    db = FaceDB()

    try:
        if args.all:
            people = db.list_people()
            if not people:
                print("[Audit] No enrolled persons found.")
                sys.exit(0)
            results = []
            for p in people:
                r = audit_gallery(p["id"], db)
                results.append(r)
                if not args.json:
                    _print_result(r)
            if args.json:
                print(json.dumps(results, indent=2))
        else:
            person_id = args.id
            row = db.get_person(person_id)
            if not row:
                print(f"[Audit] Person not found: {person_id}")
                sys.exit(1)

            if args.repair:
                r = audit_gallery(person_id, db)
                removed = repair_gallery(person_id, db, mode="remove")
                if not args.json:
                    _print_result(r, repair_count=removed)
                else:
                    print(json.dumps({**r, "removed": removed}, indent=2))
            else:
                r = audit_gallery(person_id, db)
                if not args.json:
                    _print_result(r)
                else:
                    print(json.dumps(r, indent=2))
    finally:
        db._conn.close()
