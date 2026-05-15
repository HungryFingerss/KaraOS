"""P0.6 migration progress invariant — ratchet guard.

Structure
---------
Each parametrize tuple activates AFTER its sub-PR migrates the global:

    P0.6.2 activates:  _persons_in_frame, _unrecognized_tracks,
                       _stranger_track_map, _track_identity,
                       _unrecognized_embeddings
    P0.6.3 activates:  _conversation, _last_greeted, _last_self_update,
                       _compact_pids
    P0.6.4 activates:  _voice_gallery, _voice_gallery_sizes,
                       _ambient_wake_pending, _emotion_agents,
                       _sessions_started
    P0.6.5 activates:  _scene_block_cache, _classifier_cache,
                       _identity_hints, _query_embedding_cache
    P0.6.6 activates:  _active_system_name, _detected_lang, _pipeline_state,
                       _active_room_session, _active_room_started_at,
                       _active_room_participants, _cloud_state,
                       _cloud_monitor_task, _cloud_failed_at, _cloud_recovered,
                       _last_face_seen, _last_user_speech_at, _last_kairos_at,
                       _last_silent_update
    P0.6.7 closure:    all globals at cap=0, permanent regression guard

At P0.6.7 all parametrize tuples are active and all caps are 0.
"""
from __future__ import annotations

import pathlib
import re

import pytest

PIPELINE_PATH = pathlib.Path(__file__).parent.parent / "pipeline.py"

# ---------------------------------------------------------------------------
# Mutation-write patterns (line-content based)
# Lines matching these patterns for a named global are "legacy write sites."
# Excludes:
#   - comment lines (stripped line starts with #)
#   - `global _name` declaration lines
#   - bare reads (function-arg pass, condition checks, return)
# ---------------------------------------------------------------------------

# Regex matches for a global name followed by a direct write indicator.
_WRITE_INDICATORS = re.compile(
    r"""
    (?:
        \[\s*[^\]]*\]\s*=          # subscript assignment: _g[k] =
      | \s*=\s*(?!={1})            # direct assignment: _g = ...  (not ==)
      | \.(?:pop|update|clear|add|discard|append|extend|setdefault)\s*\(
    )
    """,
    re.VERBOSE,
)


def _scan_legacy_mutations(global_name: str) -> list[tuple[int, str]]:
    """Return (lineno, stripped_line) for every direct legacy write to global_name.

    Excludes:
    - comment lines
    - `global _name` declaration lines (scope declarations)
    - lines where global_name appears only as a function argument (not write target)
    """
    src = PIPELINE_PATH.read_text(encoding="utf-8")
    results: list[tuple[int, str]] = []
    for lineno, raw_line in enumerate(src.splitlines(), start=1):
        stripped = raw_line.strip()
        # Skip comments and docstrings
        if stripped.startswith("#"):
            continue
        # Skip `global _name` declarations
        if re.match(r"global\b", stripped) and global_name in stripped:
            continue
        # Skip lines that don't mention the global at all
        if global_name not in stripped:
            continue
        # Check if the global appears as a write target or mutated via method
        # Find the position of the global name in the line
        idx = stripped.find(global_name)
        while idx != -1:
            after = stripped[idx + len(global_name):]
            if _WRITE_INDICATORS.match(after):
                results.append((lineno, stripped[:120]))
                break
            idx = stripped.find(global_name, idx + 1)
    return results


# ---------------------------------------------------------------------------
# Parametrized test cases — POPULATED by sub-PRs after migration.
#
# Format per tuple: (global_name, cap, description)
#   global_name: str   — the pipeline.py global being guarded
#   cap: int           — max allowed legacy mutations remaining (0 = fully migrated)
#   description: str   — human-readable note for failure messages
#
# At P0.6.1: empty list (no globals yet migrated). Sub-PRs add entries here.
# At P0.6.7: 25 entries, all cap=0.
# ---------------------------------------------------------------------------

_MIGRATED_GLOBALS: list[tuple[str, int, str]] = [
    # Populated by P0.6.2 – P0.6.7. Example format once P0.6.2 lands:
    # ("_persons_in_frame",       0, "P0.6.2 PresenceStore migration complete"),
    # ("_unrecognized_tracks",    0, "P0.6.2 TrackStore migration complete"),
    # ("_stranger_track_map",     0, "P0.6.2 TrackStore migration complete"),
    # ("_track_identity",         0, "P0.6.2 TrackStore migration complete"),
    # ("_unrecognized_embeddings",0, "P0.6.2 TrackStore migration complete"),
]


class TestLegacyMutationProgress:
    @pytest.mark.parametrize("global_name,cap,description", _MIGRATED_GLOBALS)
    def test_no_legacy_mutations_remain(
        self, global_name: str, cap: int, description: str
    ) -> None:
        """Migrated globals must have zero direct write sites in pipeline.py."""
        found = _scan_legacy_mutations(global_name)
        assert len(found) <= cap, (
            f"[P0.6] {global_name}: {len(found)} legacy mutation(s) found "
            f"(cap={cap}). {description}.\n"
            + "\n".join(f"  L{ln}: {src}" for ln, src in found)
        )

    @pytest.mark.parametrize("global_name,cap,description", _MIGRATED_GLOBALS)
    def test_pipeline_path_exists(
        self, global_name: str, cap: int, description: str
    ) -> None:
        """Sanity: pipeline.py must be readable for the scan to be meaningful."""
        assert PIPELINE_PATH.exists(), f"pipeline.py not found at {PIPELINE_PATH}"
        _ = global_name  # referenced to satisfy parametrize
