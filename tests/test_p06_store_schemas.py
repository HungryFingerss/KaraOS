"""P0.6.7 closure — per-Store EXPECTED_FIELDS schema invariants.

Each Store's owned-field set is pinned to its documented contract.  Adding or
removing a field without updating the corresponding EXPECTED_FIELDS set here
fails the test — forcing a deliberate decision rather than a silent schema
drift.

Test shape differs per Store, matching its own invariants:
- Cloud-bundle / room-triple-tuple stores (PipelineStateStore) pin all 14
  owned scalars + sets.
- Dual-dict atomic stores (VoiceGalleryStore) pin the (gallery, sizes) pair.
- Multi-collection stores (ConversationStore, PerPersonAgentStore) pin every
  owned dict/set.
- Single-collection stores (PresenceStore, TrackStore, CacheStore) pin the
  inner dict + any sidecar counters.

Plus dataclass schemas (PresenceEntry/TrackEntry + their snapshots,
CloudSnapshot) are pinned because they form the public read surface.
"""
from __future__ import annotations

import dataclasses


# ── Base-class field every Store must carry ──────────────────────────────
_BASE_FIELDS = {"_lock"}


def _owned_fields(instance) -> set[str]:
    """Return the set of attributes assigned in __init__ (excluding _lock)."""
    return set(vars(instance).keys()) - _BASE_FIELDS


# ── PresenceStore ────────────────────────────────────────────────────────

class TestPresenceStoreSchema:
    EXPECTED_FIELDS = {"_data"}
    EXPECTED_ENTRY_FIELDS = {
        "name", "last_seen", "last_recognized_at", "conf", "source",
    }
    EXPECTED_SNAPSHOT_FIELDS = {
        "person_id", "name", "last_seen", "last_recognized_at", "conf", "source",
    }

    def test_owned_fields_match(self) -> None:
        from core.presence_store import PresenceStore
        store = PresenceStore()
        assert _owned_fields(store) == self.EXPECTED_FIELDS, (
            f"PresenceStore owned fields drifted. "
            f"Got {_owned_fields(store)}, expected {self.EXPECTED_FIELDS}. "
            "Update test_p06_store_schemas.py if intentional."
        )

    def test_entry_dataclass_fields(self) -> None:
        from core.presence_store import PresenceEntry
        names = {f.name for f in dataclasses.fields(PresenceEntry)}
        assert names == self.EXPECTED_ENTRY_FIELDS

    def test_snapshot_dataclass_fields(self) -> None:
        from core.presence_store import PresenceSnapshot
        names = {f.name for f in dataclasses.fields(PresenceSnapshot)}
        assert names == self.EXPECTED_SNAPSHOT_FIELDS


# ── TrackStore ──────────────────────────────────────────────────────────

class TestTrackStoreSchema:
    EXPECTED_FIELDS = {"_data"}
    EXPECTED_ENTRY_FIELDS = {
        "last_seen", "embedding", "stranger_pid", "identity_pid",
    }
    EXPECTED_SNAPSHOT_FIELDS = {
        "track_id", "last_seen", "embedding", "stranger_pid", "identity_pid",
    }

    def test_owned_fields_match(self) -> None:
        from core.track_store import TrackStore
        store = TrackStore()
        assert _owned_fields(store) == self.EXPECTED_FIELDS

    def test_entry_dataclass_fields(self) -> None:
        from core.track_store import TrackEntry
        names = {f.name for f in dataclasses.fields(TrackEntry)}
        assert names == self.EXPECTED_ENTRY_FIELDS

    def test_snapshot_dataclass_fields(self) -> None:
        from core.track_store import TrackSnapshot
        names = {f.name for f in dataclasses.fields(TrackSnapshot)}
        assert names == self.EXPECTED_SNAPSHOT_FIELDS


# ── ConversationStore ───────────────────────────────────────────────────

class TestConversationStoreSchema:
    EXPECTED_FIELDS = {
        "_history",
        "_last_greeted",
        "_last_self_update",
        "_compact_pids",
    }

    def test_owned_fields_match(self) -> None:
        from core.conversation_store import ConversationStore
        store = ConversationStore()
        assert _owned_fields(store) == self.EXPECTED_FIELDS, (
            f"ConversationStore owned fields drifted. "
            f"Got {_owned_fields(store)}, expected {self.EXPECTED_FIELDS}."
        )


# ── VoiceGalleryStore ───────────────────────────────────────────────────

class TestVoiceGalleryStoreSchema:
    EXPECTED_FIELDS = {"_voice_gallery", "_voice_gallery_sizes"}

    def test_owned_fields_match(self) -> None:
        from core.voice_gallery_store import VoiceGalleryStore
        store = VoiceGalleryStore()
        assert _owned_fields(store) == self.EXPECTED_FIELDS, (
            "VoiceGalleryStore atomic pair drifted — the (gallery, sizes) "
            "invariant requires both fields exactly."
        )


# ── PerPersonAgentStore ─────────────────────────────────────────────────

class TestPerPersonAgentStoreSchema:
    EXPECTED_FIELDS = {
        "_emotion_agents",
        "_sessions_started",
        "_ambient_wake_pending",
    }

    def test_owned_fields_match(self) -> None:
        from core.per_person_agent_store import PerPersonAgentStore
        store = PerPersonAgentStore()
        assert _owned_fields(store) == self.EXPECTED_FIELDS


# ── CacheStore (×4 instances in pipeline) ───────────────────────────────

class TestCacheStoreSchema:
    EXPECTED_FIELDS = {
        "_name", "_ttl", "_max_entries", "_data", "_hits", "_misses",
    }

    def test_owned_fields_match(self) -> None:
        from core.cache_store import CacheStore
        store = CacheStore("test")
        assert _owned_fields(store) == self.EXPECTED_FIELDS, (
            f"CacheStore owned fields drifted. Got {_owned_fields(store)}, "
            f"expected {self.EXPECTED_FIELDS}."
        )

    def test_pipeline_instantiates_four_caches(self) -> None:
        """All four pipeline instances pin the same EXPECTED_FIELDS."""
        import pipeline
        for attr in (
            "_identity_hints_store",
            "_query_embedding_store",
            "_scene_block_store",
            "_classifier_cache_store",
        ):
            inst = getattr(pipeline, attr, None)
            assert inst is not None, f"pipeline.{attr} missing"
            assert _owned_fields(inst) == self.EXPECTED_FIELDS, (
                f"pipeline.{attr} field set drifted"
            )


# ── PipelineStateStore ──────────────────────────────────────────────────

class TestPipelineStateStoreSchema:
    EXPECTED_FIELDS = {
        # cloud-bundle (4)
        "_cloud_state",
        "_cloud_failed_at",
        "_cloud_recovered",
        "_cloud_monitor_task",
        # pipeline FSM (1)
        "_pipeline_state",
        # system identity / language (2)
        "_active_system_name",
        "_detected_lang",
        # room-triple-tuple (3)
        "_active_room_session",
        "_active_room_started_at",
        "_active_room_participants",
        # timestamps (4)
        "_last_face_seen",
        "_last_user_speech_at",
        "_last_kairos_at",
        "_last_silent_update",
    }
    EXPECTED_CLOUD_SNAPSHOT_FIELDS = {
        "cloud_state", "cloud_failed_at", "cloud_monitor_task", "cloud_recovered",
    }

    def test_owned_fields_match(self) -> None:
        from core.pipeline_state_store import PipelineStateStore
        store = PipelineStateStore()
        assert _owned_fields(store) == self.EXPECTED_FIELDS, (
            f"PipelineStateStore owned fields drifted. "
            f"Got {_owned_fields(store)}, expected {self.EXPECTED_FIELDS}. "
            "The 14-field bundle is load-bearing — cloud-bundle and "
            "room-triple-tuple atomicity invariants depend on it."
        )

    def test_cloud_snapshot_dataclass_fields(self) -> None:
        from core.pipeline_state_store import CloudSnapshot
        names = {f.name for f in dataclasses.fields(CloudSnapshot)}
        assert names == self.EXPECTED_CLOUD_SNAPSHOT_FIELDS

    def test_field_count_is_fourteen(self) -> None:
        """Explicit count guard — P0.6.6 migrated exactly 14 globals."""
        assert len(self.EXPECTED_FIELDS) == 14


# ── VisionFrameStore ────────────────────────────────────────────────────

class TestVisionFrameStoreSchema:
    EXPECTED_FIELDS = {"_frame", "_frame_time", "_prev_det_count"}

    def test_owned_fields_match(self) -> None:
        from core.vision_frame_store import VisionFrameStore
        store = VisionFrameStore()
        assert _owned_fields(store) == self.EXPECTED_FIELDS, (
            f"VisionFrameStore owned fields drifted. "
            f"Got {_owned_fields(store)}, expected {self.EXPECTED_FIELDS}. "
            "Producer-copy invariant is anchored to _frame — adding a field "
            "without updating the AST source-inspection test risks racing "
            "consumers against a mutable ndarray."
        )
