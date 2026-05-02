"""
person_lifecycle.py — Single authoritative path for person deletion.

All code that removes a person must call delete_person_everywhere() so that
every store (faces.db, brain.db, Kuzu graph, shadow_persons, household_facts)
is cleaned atomically. New tables that reference persons must add a delete
hook here.
"""
from __future__ import annotations

from core.db import FaceDB
from core.brain_agent import BrainOrchestrator


def delete_person_everywhere(
    person_id: str,
    person_name: str,
    faces_db: FaceDB,
    brain_orch: BrainOrchestrator,
) -> dict:
    """Remove every record of person_id from every store.

    Returns a summary dict with keys: faces, brain_rows, shadows, graph.
    Callers should log or print the summary.
    """
    summary: dict = {}

    # Name-collision guard for the Kuzu graph delete.
    # Entity's primary key in Kuzu is `name`, so delete_person_entity(name)
    # would wipe the graph node of any OTHER enrolled person who shares this
    # name. Check for collisions BEFORE we delete our own persons row so the
    # comparison is faithful.
    name_shared = faces_db._conn.execute(
        "SELECT COUNT(*) FROM persons WHERE name = ? AND id != ?",
        (person_name, person_id),
    ).fetchone()[0]

    # 1. faces.db — embeddings, voice, conversation, persons row
    faces_db.delete_person(person_id)
    summary["faces"] = "ok"

    # 2. brain.db — knowledge, episodes, presence, prefs, nudges, mentions,
    #               inter_person_relationships, household_facts source_speakers
    brain_rows = brain_orch.brain_db.delete_person_data([person_id])
    summary["brain_rows"] = brain_rows

    # 3. shadow_persons — remove references to this person from known_via JSON
    shadows = brain_orch.brain_db.prune_shadows_mentioning(person_id, person_name)
    summary["shadows"] = shadows

    # 4. Kuzu graph — delete Entity node for person_name + all its edges
    # Skip if another enrolled person still uses this name (avoid cross-deletion).
    if name_shared:
        print(
            f"[Lifecycle] Skipping graph delete for '{person_name}': "
            f"{name_shared} other enrolled person(s) share this name"
        )
        summary["graph"] = f"skipped (name shared by {name_shared} other(s))"
    else:
        ok = brain_orch.graph_db.delete_person_entity(person_name)
        summary["graph"] = "ok" if ok else "error (see logs)"

    return summary
