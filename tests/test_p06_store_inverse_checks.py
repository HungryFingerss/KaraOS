"""P0.6.7 closure — per-Store inverse-check (paired-write discipline).

For each Store, the set of methods that write each owned field is enumerated.
The AST scan asserts BOTH directions:

  forward — every enumerated writer actually contains a write to the field.
  inverse — every method NOT in the enumerated writer set contains NO writes
            to the field.

A future method that adds a write to an owned field without being enumerated
fails the inverse direction.  This is the same discipline that P0.5's
`PAIRED_WRITE_METHODS` enforced on FaceDB — generalized to all 7 P0.6 Stores.

Test shape differs per Store, matching its actual invariants:

- PipelineStateStore: cloud-bundle (4 fields) and room-triple-tuple (3 fields)
  have atomic-cross-field invariants — paired-write discipline.  Plus 7
  unbundled scalar fields each get standard writer enumeration.
- VoiceGalleryStore: (gallery, sizes) pair — every writer must touch BOTH
  fields atomically.
- ConversationStore, PerPersonAgentStore, PresenceStore, TrackStore,
  CacheStore: simpler single-field invariants — per-field writer enumeration.
"""
from __future__ import annotations

import ast
import importlib
import inspect
import pathlib


REPO_ROOT = pathlib.Path(__file__).parent.parent

# Method-call attributes that count as mutators when applied to a field.
_MUTATOR_METHODS = {
    "pop", "popitem", "clear", "add", "discard", "remove",
    "append", "extend", "setdefault", "update", "insert",
    "move_to_end", "__setitem__", "__delitem__",
}


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------

def _root_self_attr(node: ast.AST) -> str | None:
    """Walk an Attribute/Subscript/Call chain down to its leftmost root.
    Return the attribute name if the chain bottoms out at `self.<X>` —
    otherwise None.
    """
    cur = node
    while True:
        if isinstance(cur, ast.Subscript):
            cur = cur.value
        elif isinstance(cur, ast.Call):
            cur = cur.func
        elif isinstance(cur, ast.Attribute):
            if isinstance(cur.value, ast.Name) and cur.value.id == "self":
                return cur.attr
            cur = cur.value
        else:
            return None


def _method_writes_field(method_node: ast.FunctionDef | ast.AsyncFunctionDef,
                          field_name: str) -> bool:
    """True if method body contains a write to self.<field_name>."""
    for node in ast.walk(method_node):
        # Assignment targets: self._x = ..., self._x[k] = ..., self._x.attr = ...
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for tgt in targets:
                if _root_self_attr(tgt) == field_name:
                    return True

        # del self._x or del self._x[k]
        elif isinstance(node, ast.Delete):
            for tgt in node.targets:
                if _root_self_attr(tgt) == field_name:
                    return True

        # self._x.mutator(...)
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in _MUTATOR_METHODS:
                if _root_self_attr(func.value) == field_name:
                    return True
    return False


def _load_class_methods(module_name: str, class_name: str
                         ) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    """Return {method_name: ast_node} for every method in the class."""
    src = (REPO_ROOT / "core" / f"{module_name}.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {
                m.name: m
                for m in node.body
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
    raise AssertionError(f"class {class_name} not found in core/{module_name}.py")


def _assert_writers(store_label: str, methods: dict, field: str,
                     expected_writers: set[str]) -> None:
    """Forward+inverse: writers exactly match the enumerated set."""
    actual = {
        name for name, node in methods.items()
        if _method_writes_field(node, field)
    }
    extra = actual - expected_writers
    missing = expected_writers - actual
    assert not extra and not missing, (
        f"[{store_label}.{field}] writer set drifted.\n"
        f"  unexpected (inverse violation): {sorted(extra)}\n"
        f"  missing (forward violation): {sorted(missing)}\n"
        "Update the enumerated set in tests/test_p06_store_inverse_checks.py "
        "if the change is intentional."
    )


# ---------------------------------------------------------------------------
# PresenceStore — single dict-of-dataclasses
# ---------------------------------------------------------------------------

class TestPresenceStoreInverse:
    EXPECTED = {
        "_data": {
            "__init__", "reset",
            "upsert_face_recognition", "upsert_voice_recognition",
            "touch_last_seen", "update_name",
            "remove", "prune_stale", "clear",
        },
    }

    def test_writers_enumerated(self) -> None:
        methods = _load_class_methods("presence_store", "PresenceStore")
        for field, expected in self.EXPECTED.items():
            _assert_writers("PresenceStore", methods, field, expected)


# ---------------------------------------------------------------------------
# TrackStore — single dict-of-dataclasses
# ---------------------------------------------------------------------------

class TestTrackStoreInverse:
    EXPECTED = {
        "_data": {
            "__init__", "reset",
            "mark_unrecognized", "set_embedding",
            "mint_stranger", "bind_identity",
            "remove_track", "prune_stale", "prune_to_active_tids",
            "prune_for_session_close", "clear",
            # P0.S1 D2.b — atomic embedding+verdict upsert.
            "upsert_embedding_with_verdict",
        },
    }

    def test_writers_enumerated(self) -> None:
        methods = _load_class_methods("track_store", "TrackStore")
        for field, expected in self.EXPECTED.items():
            _assert_writers("TrackStore", methods, field, expected)


# ---------------------------------------------------------------------------
# ConversationStore — four owned collections
# ---------------------------------------------------------------------------

class TestConversationStoreInverse:
    EXPECTED = {
        "_history": {
            "__init__", "reset",
            "set_history", "append_turns", "pop_history",
            "init_empty", "ensure_history_loaded",
            "clear_all_history", "clear_all",
        },
        "_last_greeted": {
            "__init__", "reset",
            "touch_greeted", "clear_all_greeted", "clear_all",
        },
        "_last_self_update": {
            "__init__", "reset",
            "touch_self_update", "clear_all_self_update", "clear_all",
        },
        "_compact_pids": {
            "__init__", "reset",
            "add_compact", "release_compact",
            "clear_all_compact", "clear_all",
        },
    }

    def test_writers_enumerated(self) -> None:
        methods = _load_class_methods("conversation_store", "ConversationStore")
        for field, expected in self.EXPECTED.items():
            _assert_writers("ConversationStore", methods, field, expected)


# ---------------------------------------------------------------------------
# VoiceGalleryStore — (gallery, sizes) atomic pair
# ---------------------------------------------------------------------------

class TestVoiceGalleryStoreInverse:
    # Every writer below MUST touch BOTH fields — paired-write discipline.
    PAIR_WRITERS = {
        "__init__", "reset",
        "set_gallery", "pop_gallery", "clear",
        "load_bulk", "reconcile",
    }

    def test_gallery_writers_enumerated(self) -> None:
        methods = _load_class_methods("voice_gallery_store", "VoiceGalleryStore")
        _assert_writers(
            "VoiceGalleryStore", methods, "_voice_gallery", self.PAIR_WRITERS,
        )

    def test_sizes_writers_enumerated(self) -> None:
        methods = _load_class_methods("voice_gallery_store", "VoiceGalleryStore")
        _assert_writers(
            "VoiceGalleryStore", methods, "_voice_gallery_sizes",
            self.PAIR_WRITERS,
        )

    def test_pair_writers_touch_both_fields(self) -> None:
        """Atomicity: every pair writer must touch BOTH _voice_gallery AND
        _voice_gallery_sizes.  A method touching only one is a divergence
        risk (readers could see a stale size paired with an old embedding)."""
        methods = _load_class_methods("voice_gallery_store", "VoiceGalleryStore")
        for writer in self.PAIR_WRITERS:
            node = methods[writer]
            touches_gallery = _method_writes_field(node, "_voice_gallery")
            touches_sizes = _method_writes_field(node, "_voice_gallery_sizes")
            assert touches_gallery and touches_sizes, (
                f"VoiceGalleryStore.{writer} writes only one of the pair "
                f"(gallery={touches_gallery}, sizes={touches_sizes}). "
                "The (gallery, sizes) atomicity invariant requires both."
            )


# ---------------------------------------------------------------------------
# PerPersonAgentStore — three owned collections
# ---------------------------------------------------------------------------

class TestPerPersonAgentStoreInverse:
    EXPECTED = {
        "_emotion_agents": {
            "__init__", "reset",
            "set_emotion_agent", "pop_emotion_agent",
            "clear_emotion_agents",
        },
        "_sessions_started": {
            "__init__", "reset",
            "add_session_started", "discard_session_started",
            "clear_sessions_started",
        },
        "_ambient_wake_pending": {
            "__init__", "reset",
            "add_ambient_wake", "discard_ambient_wake",
            "clear_ambient_wake",
        },
    }

    def test_writers_enumerated(self) -> None:
        methods = _load_class_methods(
            "per_person_agent_store", "PerPersonAgentStore",
        )
        for field, expected in self.EXPECTED.items():
            _assert_writers("PerPersonAgentStore", methods, field, expected)


# ---------------------------------------------------------------------------
# CacheStore — single ordered-dict with sidecar counters
# ---------------------------------------------------------------------------

class TestCacheStoreInverse:
    EXPECTED = {
        "_data": {
            "__init__", "reset",
            "peek",   # TTL eviction (`del self._data[key]` on expired entry)
            "set", "discard", "clear",
        },
        # _hits / _misses are observability counters (documented read-side
        # mutation — see CacheStore module docstring + # OBSERVABILITY:
        # annotations on the increment lines).
        "_hits": {"__init__", "reset", "peek"},
        "_misses": {"__init__", "reset", "peek"},
    }

    def test_writers_enumerated(self) -> None:
        methods = _load_class_methods("cache_store", "CacheStore")
        for field, expected in self.EXPECTED.items():
            _assert_writers("CacheStore", methods, field, expected)


# ---------------------------------------------------------------------------
# PipelineStateStore — cloud-bundle, room-triple-tuple, + 7 unbundled scalars
# ---------------------------------------------------------------------------

class TestPipelineStateStoreInverse:

    # NOTE: PipelineStateStore.__init__ first calls self.reset() (which
    # writes every owned field), then conditionally writes _cloud_state and
    # _pipeline_state when initial_* kwargs are supplied (P0.6.6 fix for
    # production-shape defaults).  So `__init__` is enumerated for those
    # two fields specifically; all other init-time writes still flow
    # through `reset`.

    # ── Cloud-bundle: 4 fields with atomic-cross-field invariant ────────
    CLOUD_BUNDLE_WRITERS = {
        "_cloud_state": {
            "__init__",  # conditional initial_cloud_state assignment
            "reset",
            "transition_to_sick", "transition_to_offline",
            "transition_to_online", "recover_online_no_flag",
            "set_cloud_state",
            "_sync_set_cloud_state",  # known sync mutator (NOT a shim)
        },
        "_cloud_failed_at": {
            "reset",
            "transition_to_sick", "set_cloud_failed_at",
        },
        "_cloud_recovered": {
            "reset",
            "transition_to_online", "consume_cloud_recovered",
            "set_cloud_recovered",
        },
        "_cloud_monitor_task": {
            "reset", "set_cloud_monitor_task",
        },
    }

    # ── Room-triple-tuple: 3 fields with atomic-cross-field invariant ──
    ROOM_TRIPLE_WRITERS = {
        "_active_room_session": {
            "reset",
            "mint_room", "end_room",
            "set_active_room_session",
            "_sync_mint_room", "_sync_clear_room",  # known sync mutators
        },
        "_active_room_started_at": {
            "reset",
            "mint_room", "end_room",
            "set_active_room_started_at",
            "_sync_mint_room", "_sync_clear_room",
        },
        "_active_room_participants": {
            "reset",
            "mint_room", "add_room_participant", "end_room",
            "set_active_room_participants",
            "_sync_mint_room", "_sync_add_room_participant",
            "_sync_clear_room",
        },
    }

    # ── Unbundled scalars: 7 fields with reset+setter pattern ────────────
    SCALAR_WRITERS = {
        # __init__ enumerated for _pipeline_state: P0.6.6 fix conditionally
        # assigns it from initial_pipeline_state kwarg.
        "_pipeline_state": {"__init__", "reset", "set_pipeline_state"},
        "_active_system_name": {"reset", "set_active_system_name"},
        "_detected_lang": {"reset", "set_detected_lang"},
        "_last_face_seen": {"reset", "set_last_face_seen"},
        "_last_user_speech_at": {"reset", "set_last_user_speech_at"},
        "_last_kairos_at": {"reset", "set_last_kairos_at"},
        "_last_silent_update": {"reset", "set_last_silent_update"},
    }

    def _methods(self) -> dict:
        return _load_class_methods("pipeline_state_store", "PipelineStateStore")

    def test_cloud_bundle_writers_enumerated(self) -> None:
        methods = self._methods()
        for field, expected in self.CLOUD_BUNDLE_WRITERS.items():
            _assert_writers("PipelineStateStore", methods, field, expected)

    def test_room_triple_tuple_writers_enumerated(self) -> None:
        methods = self._methods()
        for field, expected in self.ROOM_TRIPLE_WRITERS.items():
            _assert_writers("PipelineStateStore", methods, field, expected)

    def test_scalar_writers_enumerated(self) -> None:
        methods = self._methods()
        for field, expected in self.SCALAR_WRITERS.items():
            _assert_writers("PipelineStateStore", methods, field, expected)

    def test_cloud_paired_writers_are_atomic(self) -> None:
        """transition_to_sick must touch BOTH cloud_state AND cloud_failed_at.
        transition_to_online must touch BOTH cloud_state AND cloud_recovered.
        Atomic pairs are load-bearing per P0.6.6 design (CloudSnapshot
        invariant)."""
        methods = self._methods()
        sick = methods["transition_to_sick"]
        assert (_method_writes_field(sick, "_cloud_state")
                and _method_writes_field(sick, "_cloud_failed_at")), (
            "transition_to_sick must write both _cloud_state and "
            "_cloud_failed_at atomically"
        )
        online = methods["transition_to_online"]
        assert (_method_writes_field(online, "_cloud_state")
                and _method_writes_field(online, "_cloud_recovered")), (
            "transition_to_online must write both _cloud_state and "
            "_cloud_recovered atomically"
        )

    def test_room_paired_writers_are_atomic(self) -> None:
        """mint_room must touch all 3 room-triple-tuple fields.
        end_room must touch all 3.  _sync_mint_room / _sync_clear_room
        same — they are the synchronous variants of those operations."""
        methods = self._methods()
        for op in ("mint_room", "end_room", "_sync_mint_room", "_sync_clear_room"):
            node = methods[op]
            assert all(
                _method_writes_field(node, f) for f in (
                    "_active_room_session",
                    "_active_room_started_at",
                    "_active_room_participants",
                )
            ), (
                f"PipelineStateStore.{op} must touch all 3 room-triple-tuple "
                "fields atomically"
            )

    def test_known_sync_mutator_sites_documented_pss(self) -> None:
        """The 4 documented sync mutators (P0.6.6 internal-use-only helpers)
        must exist and be enumerated in the writer sets above.  They are
        load-bearing — pipeline.py's _open_session / _close_session call
        them from sync contexts where create_task would defer the write."""
        methods = self._methods()
        for sync_helper in (
            "_sync_set_cloud_state",
            "_sync_mint_room",
            "_sync_add_room_participant",
            "_sync_clear_room",
        ):
            assert sync_helper in methods, (
                f"PipelineStateStore.{sync_helper} missing — required by "
                "pipeline.py's synchronous lifecycle paths"
            )


# ---------------------------------------------------------------------------
# VisionFrameStore — frame + ts (atomic pair) + prev_det_count (scalar)
# ---------------------------------------------------------------------------

class TestVisionFrameStoreInverse:
    # _frame and _frame_time form an atomic pair — set_frame writes both
    # under one lock acquisition.  clear_frame writes both.  reset writes
    # both.  No other method may touch either field.
    FRAME_PAIR_WRITERS = {"reset", "set_frame", "clear_frame"}
    SCALAR_WRITERS = {
        "_prev_det_count": {
            "reset", "set_prev_det_count", "_sync_set_prev_det_count",
        },
    }

    # NOTE: VisionFrameStore.__init__ delegates to self.reset() (same
    # pattern as PipelineStateStore), so AST-attributed writes show up on
    # `reset` only.

    def _methods(self) -> dict:
        return _load_class_methods("vision_frame_store", "VisionFrameStore")

    def test_frame_writers_enumerated(self) -> None:
        methods = self._methods()
        _assert_writers(
            "VisionFrameStore", methods, "_frame", self.FRAME_PAIR_WRITERS,
        )

    def test_frame_time_writers_enumerated(self) -> None:
        methods = self._methods()
        _assert_writers(
            "VisionFrameStore", methods, "_frame_time", self.FRAME_PAIR_WRITERS,
        )

    def test_prev_det_count_writers_enumerated(self) -> None:
        methods = self._methods()
        for field, expected in self.SCALAR_WRITERS.items():
            _assert_writers("VisionFrameStore", methods, field, expected)

    def test_frame_pair_atomic(self) -> None:
        """set_frame must write both _frame AND _frame_time atomically.
        clear_frame same.  A method touching only one would let consumers
        see frame=N+1 paired with time=N (stale-check would gate the wrong
        frame) or vice-versa."""
        methods = self._methods()
        for op in ("set_frame", "clear_frame"):
            node = methods[op]
            assert (_method_writes_field(node, "_frame")
                    and _method_writes_field(node, "_frame_time")), (
                f"VisionFrameStore.{op} must touch BOTH _frame and "
                "_frame_time atomically (producer-consumer pair invariant)"
            )

    def test_sync_prev_det_count_helper_documented(self) -> None:
        """_sync_set_prev_det_count is the load-bearing sync entry point for
        pipeline._expire_stale_sessions (sync def function).  Must exist."""
        methods = self._methods()
        assert "_sync_set_prev_det_count" in methods, (
            "VisionFrameStore._sync_set_prev_det_count missing — required "
            "by pipeline._expire_stale_sessions (sync context)"
        )
