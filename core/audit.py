"""
core/audit.py — Gallery outlier detection.

audit_gallery(person_id, db) → dict  — analysis with outlier list

For the destructive remove-outliers operation, use `FaceDB.prune_outlier_embeddings`
which is the P0.5-correct paired-write site (SQL-first transaction + FAISS rebuild
+ sentinel discipline). P0.S9 D1 consolidated by removing the local `repair_gallery`
duplicate; see `audit_person.py --repair` flag for CLI usage.
"""
from __future__ import annotations

import numpy as np


def audit_gallery(person_id: str, db) -> dict:
    """Compute centroid-based outlier analysis for a person's face embeddings.

    Returns a dict with keys: person_id, total, mean_distance, std_distance, outliers.
    Each outlier entry: row_id, source, confidence_at_write, captured_at, distance_from_centroid.
    """
    rows = db._conn.execute(
        "SELECT id, vector, source, confidence_at_write, captured_at "
        "FROM embeddings WHERE person_id = ? AND vector IS NOT NULL "
        "ORDER BY captured_at",
        (person_id,),
    ).fetchall()

    if len(rows) < 2:
        return {
            "person_id": person_id,
            "total": len(rows),
            "mean_distance": 0.0,
            "std_distance": 0.0,
            "outliers": [],
            "note": "Need ≥2 embeddings for outlier analysis.",
        }

    embs = [np.frombuffer(r[1], dtype=np.float32).copy() for r in rows]
    centroid = np.mean(embs, axis=0)
    norm = np.linalg.norm(centroid)
    if norm > 0:
        centroid /= norm

    distances = [float(1.0 - np.dot(e / max(np.linalg.norm(e), 1e-9), centroid)) for e in embs]
    mean_d = float(np.mean(distances))
    std_d = float(np.std(distances))
    threshold = mean_d + 2 * std_d

    outliers = [
        {
            "row_id":               rows[i][0],
            "source":               rows[i][2],
            "confidence_at_write":  float(rows[i][3]),
            "captured_at":          float(rows[i][4]),
            "distance_from_centroid": distances[i],
        }
        for i in range(len(rows))
        if distances[i] > threshold
    ]

    return {
        "person_id":     person_id,
        "total":         len(rows),
        "mean_distance": mean_d,
        "std_distance":  std_d,
        "threshold":     threshold,
        "outliers":      outliers,
    }

