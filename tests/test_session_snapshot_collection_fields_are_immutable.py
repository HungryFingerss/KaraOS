"""Bundle 5 D5 (MF8) — AST + behavioral invariant: the 3 collection-typed
fields on `SessionSnapshot` are immutable tuples, not lists.

Rationale (Pre-P1 Bundle 5 MF8): `SessionSnapshot` is `frozen=True` and
documented "safe to hold across await points." A frozen dataclass still lets
a caller mutate a `list` field in place (`snap.recent_voice_confs.append(...)`)
— silently corrupting a snapshot that other coroutines may hold. Annotating
the 3 collection fields `tuple` + materializing them via `tuple(...)` in
`_to_snapshot` makes the snapshot genuinely immutable. The owner `Session`
keeps `list` (it's the mutable working copy).

Static: AST-assert the 3 SessionSnapshot fields are annotated `tuple`.
Behavioral: a snapshot built via `_to_snapshot` has tuple fields (no `.append`).
Self-tests: forward (synthetic `list` annotation fires) + inverse (tuple passes).
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SESSION_STATE_PATH = REPO_ROOT / "core" / "session_state.py"

IMMUTABLE_SNAPSHOT_FIELDS = ("recent_voice_confs", "core_memory", "recent_attributions")


def _annotation_base_name(node: ast.AST) -> str | None:
    """Return the base type name of an annotation (`tuple`, `list`, ...).

    Handles bare `tuple` (ast.Name) and subscripted `tuple[...]` (ast.Subscript).
    """
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Subscript):
        return _annotation_base_name(node.value)
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        # String annotation ("tuple") — parse the inner expression.
        try:
            inner = ast.parse(node.value, mode="eval").body
        except SyntaxError:
            return None
        return _annotation_base_name(inner)
    return None


def _snapshot_field_annotations(source: str) -> dict[str, str | None]:
    """Map each SessionSnapshot AnnAssign field name → its base annotation name."""
    tree = ast.parse(source)
    result: dict[str, str | None] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "SessionSnapshot":
            for stmt in node.body:
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                    result[stmt.target.id] = _annotation_base_name(stmt.annotation)
            break
    return result


def test_d5_snapshot_collection_fields_annotated_tuple() -> None:
    """D5 (static) — the 3 SessionSnapshot collection fields are annotated `tuple`."""
    source = SESSION_STATE_PATH.read_text(encoding="utf-8")
    annotations = _snapshot_field_annotations(source)
    assert annotations, "SessionSnapshot class not found in core/session_state.py"
    bad = {
        name: annotations.get(name)
        for name in IMMUTABLE_SNAPSHOT_FIELDS
        if annotations.get(name) != "tuple"
    }
    assert not bad, (
        f"SessionSnapshot fields must be annotated `tuple` (immutable snapshot); "
        f"found non-tuple annotations: {bad}. A `list` field lets a holder mutate "
        f"a frozen snapshot in place."
    )


def test_d5_behavioral_to_snapshot_produces_tuple_fields() -> None:
    """D5 (behavioral) — a snapshot built via _to_snapshot has tuple fields (no .append)."""
    from core.session_state import Session, _to_snapshot

    s = Session(
        person_id="p1",
        person_name="Alice",
        person_type="known",
        session_type="voice",
        started_at=0.0,
        last_face_seen=0.0,
        last_spoke_at=0.0,
    )
    s.recent_voice_confs.append(0.9)
    s.core_memory.append("fact")
    s.recent_attributions.append("voice")

    snap = _to_snapshot(s)

    for field in IMMUTABLE_SNAPSHOT_FIELDS:
        value = getattr(snap, field)
        assert isinstance(value, tuple), (
            f"SessionSnapshot.{field} must be a tuple, got {type(value).__name__}"
        )
        assert not hasattr(value, "append"), (
            f"SessionSnapshot.{field} must be immutable (no .append)"
        )

    # Snapshot must be a copy, not a reference to the owner's list — mutating the
    # owner after snapshot must NOT change the snapshot.
    s.recent_voice_confs.append(0.5)
    assert snap.recent_voice_confs == (0.9,), (
        "snapshot leaked a reference to the owner's mutable list"
    )


# --- Self-tests ---

def test_d5_self_test_forward_list_annotation_fires() -> None:
    """Forward: a synthetic SessionSnapshot with a `list` field is flagged."""
    src = (
        "import dataclasses\n"
        "@dataclasses.dataclass(frozen=True)\n"
        "class SessionSnapshot:\n"
        "    recent_voice_confs: list\n"
        "    core_memory: tuple\n"
        "    recent_attributions: tuple\n"
    )
    annotations = _snapshot_field_annotations(src)
    bad = {
        name: annotations.get(name)
        for name in IMMUTABLE_SNAPSHOT_FIELDS
        if annotations.get(name) != "tuple"
    }
    assert bad == {"recent_voice_confs": "list"}, (
        f"forward self-test should flag the `list` field, got {bad}"
    )


def test_d5_self_test_inverse_all_tuple_passes() -> None:
    """Inverse: a synthetic SessionSnapshot with all-tuple fields is clean."""
    src = (
        "import dataclasses\n"
        "@dataclasses.dataclass(frozen=True)\n"
        "class SessionSnapshot:\n"
        "    recent_voice_confs: tuple\n"
        "    core_memory: tuple\n"
        "    recent_attributions: tuple\n"
    )
    annotations = _snapshot_field_annotations(src)
    bad = {
        name: annotations.get(name)
        for name in IMMUTABLE_SNAPSHOT_FIELDS
        if annotations.get(name) != "tuple"
    }
    assert not bad, f"inverse self-test should be clean, got {bad}"
