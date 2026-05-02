"""
repair_gallery.py — Gallery health audit and optional outlier pruning.

Usage:
    python repair_gallery.py                    # audit all persons, report only
    python repair_gallery.py --person jagan_001 # audit one person only
    python repair_gallery.py --prune            # remove outlier embeddings (all persons)
    python repair_gallery.py --prune --sigma 1.5 # tighter threshold
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.db import FaceDB


def _bar(counts: dict, total: int, width: int = 20) -> str:
    if not counts:
        return ""
    parts = []
    for src, n in sorted(counts.items(), key=lambda x: -x[1]):
        pct = n / total * 100 if total else 0
        parts.append(f"{src}={n}({pct:.0f}%)")
    return "  ".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser(description="Face gallery audit and repair")
    parser.add_argument("--person", default=None, help="Audit a single person by ID")
    parser.add_argument("--prune",  action="store_true",
                        help="Delete outlier embeddings (requires confirmation)")
    parser.add_argument("--sigma",  type=float, default=2.0,
                        help="Sigma threshold for outlier detection (default: 2.0)")
    args = parser.parse_args()

    db = FaceDB()
    results = db.gallery_audit(person_id=args.person, sigma=args.sigma)

    if not results:
        print("No embeddings found in gallery.")
        db._conn.close()
        return

    total_outliers = sum(len(r["outlier_row_ids"]) for r in results)

    print(f"\n{'─'*72}")
    print(f"{'PERSON':<30} {'TOTAL':>5}  {'SOURCES':<35}  {'OUTLIERS':>8}")
    print(f"{'─'*72}")
    for r in results:
        name_col  = f"{r['name']} ({r['person_id']})"[:30]
        src_col   = _bar(r["by_source"], r["total"], width=35)[:35]
        out_col   = str(len(r["outlier_row_ids"])) if r["outlier_row_ids"] else "-"
        print(f"{name_col:<30} {r['total']:>5}  {src_col:<35}  {out_col:>8}")
        if r["outlier_row_ids"]:
            print(f"  {'':30} outlier row IDs: {r['outlier_row_ids'][:10]}"
                  + (" ..." if len(r["outlier_row_ids"]) > 10 else ""))
    print(f"{'─'*72}")
    print(f"Total persons: {len(results)}  |  Total outliers: {total_outliers}  |  sigma={args.sigma}")

    if total_outliers and not args.prune:
        print(f"\nTip: run with --prune to remove {total_outliers} outlier embedding(s).")

    if args.prune:
        if total_outliers == 0:
            print("\nNo outliers to prune.")
        else:
            print(f"\nThis will delete {total_outliers} outlier embedding(s) and rebuild FAISS.")
            answer = input("Continue? [y/N] ").strip().lower()
            if answer != "y":
                print("Aborted.")
            else:
                removed = 0
                for r in results:
                    if r["outlier_row_ids"]:
                        n = db.prune_outlier_embeddings(r["person_id"], sigma=args.sigma)
                        removed += n
                        print(f"  {r['name']}: removed {n} outlier(s)")
                print(f"\nDone — removed {removed} embedding(s) total. FAISS rebuilt.")

    db._conn.close()


if __name__ == "__main__":
    main()
