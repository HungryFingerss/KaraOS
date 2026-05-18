"""Behavioural unit tests for core/pipeline_state_store.py — P0.6.6."""
import asyncio
import time

import pytest

from core.pipeline_state_store import CloudSnapshot, PipelineStateStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Reset semantics
# ---------------------------------------------------------------------------

class TestReset:
    def test_reset_initialises_cloud_state_to_none(self):
        store = PipelineStateStore()
        assert store.peek_cloud_state() is None

    def test_reset_initialises_cloud_failed_at_zero(self):
        store = PipelineStateStore()
        assert store.peek_cloud_failed_at() == 0.0

    def test_reset_initialises_cloud_recovered_false(self):
        store = PipelineStateStore()
        assert store.peek_cloud_recovered() is False

    def test_reset_initialises_pipeline_state_none(self):
        store = PipelineStateStore()
        assert store.peek_pipeline_state() is None

    def test_reset_initialises_active_system_name_to_default(self):
        from core.config import DEFAULT_SYSTEM_NAME
        store = PipelineStateStore()
        assert store.peek_active_system_name() == DEFAULT_SYSTEM_NAME

    def test_reset_initialises_detected_lang_en(self):
        store = PipelineStateStore()
        assert store.peek_detected_lang() == "en"

    def test_reset_clears_room_session(self):
        store = PipelineStateStore()
        _run(store.set_active_room_session("room_abc"))
        store.reset()
        assert store.peek_active_room_session() is None

    def test_reset_clears_room_participants(self):
        store = PipelineStateStore()
        _run(store.set_active_room_participants({"p1", "p2"}))
        store.reset()
        assert store.peek_active_room_participants() == set()

    def test_reset_clears_timestamps(self):
        store = PipelineStateStore()
        _run(store.set_last_face_seen(999.9))
        _run(store.set_last_kairos_at(888.8))
        store.reset()
        assert store.peek_last_face_seen() == 0.0
        assert store.peek_last_kairos_at() == 0.0


# ---------------------------------------------------------------------------
# Cloud transition methods
# ---------------------------------------------------------------------------

class TestCloudTransitions:
    def test_transition_to_sick_sets_cloud_state(self):
        import sys
        if "pipeline" not in sys.modules:
            pytest.skip("pipeline not importable (torchaudio DLL)")
        import pipeline
        store = PipelineStateStore()
        ts = time.time()
        _run(store.transition_to_sick(ts))
        assert store.peek_cloud_state() == pipeline.CloudState.SICK
        assert store.peek_cloud_failed_at() == ts

    def test_transition_to_offline_sets_cloud_state(self):
        import sys
        if "pipeline" not in sys.modules:
            pytest.skip("pipeline not importable (torchaudio DLL)")
        import pipeline
        store = PipelineStateStore()
        _run(store.transition_to_sick(time.time()))
        _run(store.transition_to_offline())
        assert store.peek_cloud_state() == pipeline.CloudState.OFFLINE

    def test_transition_to_online_sets_cloud_state_and_recovered_flag(self):
        import sys
        if "pipeline" not in sys.modules:
            pytest.skip("pipeline not importable (torchaudio DLL)")
        import pipeline
        store = PipelineStateStore()
        _run(store.transition_to_sick(time.time()))
        _run(store.transition_to_online())
        assert store.peek_cloud_state() == pipeline.CloudState.ONLINE
        assert store.peek_cloud_recovered() is True

    def test_production_init_sets_watching_and_online(self):
        """P0.6.6 fix: PipelineStateStore must accept initial_pipeline_state
        and initial_cloud_state kwargs so the module-level instantiation in
        pipeline.py can pre-load production defaults — otherwise
        peek_pipeline_state() returns None at boot and the greeting gate
        (`== PipelineState.WATCHING`) never fires.

        Live boot symptom (2026-05-16): Jagan recognized via background
        scan but greeting branch silently skipped because the FSM never
        reached WATCHING.
        """
        import sys
        if "pipeline" not in sys.modules:
            pytest.skip("pipeline not importable (torchaudio DLL)")
        import pipeline
        store = PipelineStateStore(
            initial_pipeline_state=pipeline.PipelineState.WATCHING,
            initial_cloud_state=pipeline.CloudState.ONLINE,
        )
        assert store.peek_pipeline_state() == pipeline.PipelineState.WATCHING
        assert store.peek_cloud_state() == pipeline.CloudState.ONLINE

    def test_bare_init_preserves_none_defaults(self):
        """Backwards-compat: bare PipelineStateStore() with no kwargs still
        gets None defaults — preserves the existing test corpus that
        constructs local stores without initial values."""
        store = PipelineStateStore()
        assert store.peek_pipeline_state() is None
        assert store.peek_cloud_state() is None

    def test_module_level_store_has_production_shape(self):
        """Smoke test: pipeline._pipeline_state_store (the module-level
        instance, NOT a fresh local one) must come up in production shape.
        This is what the greeting gate actually reads from."""
        import sys
        if "pipeline" not in sys.modules:
            pytest.skip("pipeline not importable (torchaudio DLL)")
        import pipeline
        assert pipeline._pipeline_state_store.peek_pipeline_state() == pipeline.PipelineState.WATCHING
        assert pipeline._pipeline_state_store.peek_cloud_state() == pipeline.CloudState.ONLINE

    def test_transition_to_online_from_online_does_not_set_recovered(self):
        """P0.6.7v2 prior-state guard: ONLINE→ONLINE must NOT set cloud_recovered.
        An idempotent call (defensive retry, scheduled re-fire) shouldn't
        signal a recovery for a transition that never happened."""
        import sys
        if "pipeline" not in sys.modules:
            pytest.skip("pipeline not importable (torchaudio DLL)")
        import pipeline
        store = PipelineStateStore()
        # Seed ONLINE without the recovered flag (mirrors the C2 path).
        _run(store.recover_online_no_flag())
        assert store.peek_cloud_recovered() is False
        # Now call transition_to_online on an already-ONLINE store.
        _run(store.transition_to_online())
        assert store.peek_cloud_state() == pipeline.CloudState.ONLINE
        # The guard must prevent cloud_recovered from flipping spuriously.
        assert store.peek_cloud_recovered() is False

    def test_recover_online_no_flag_does_not_set_recovered(self):
        import sys
        if "pipeline" not in sys.modules:
            pytest.skip("pipeline not importable (torchaudio DLL)")
        import pipeline
        store = PipelineStateStore()
        _run(store.transition_to_sick(time.time()))
        _run(store.recover_online_no_flag())
        assert store.peek_cloud_state() == pipeline.CloudState.ONLINE
        assert store.peek_cloud_recovered() is False

    def test_consume_cloud_recovered_returns_and_clears_flag(self):
        import sys
        if "pipeline" not in sys.modules:
            pytest.skip("pipeline not importable (torchaudio DLL)")
        store = PipelineStateStore()
        _run(store.transition_to_online())
        assert _run(store.consume_cloud_recovered()) is True
        assert _run(store.consume_cloud_recovered()) is False
        assert store.peek_cloud_recovered() is False

    def test_consume_cloud_recovered_returns_false_when_not_set(self):
        store = PipelineStateStore()
        assert _run(store.consume_cloud_recovered()) is False

    def test_transition_to_sick_is_atomic_via_snapshot(self):
        import sys
        if "pipeline" not in sys.modules:
            pytest.skip("pipeline not importable (torchaudio DLL)")
        import pipeline
        store = PipelineStateStore()
        ts = 12345.0
        _run(store.transition_to_sick(ts))
        snap = store.peek_cloud_snapshot()
        assert snap.cloud_state == pipeline.CloudState.SICK
        assert snap.cloud_failed_at == ts


# ---------------------------------------------------------------------------
# CloudSnapshot immutability
# ---------------------------------------------------------------------------

class TestCloudSnapshot:
    def test_cloud_snapshot_is_frozen(self):
        snap = CloudSnapshot(cloud_state=None, cloud_failed_at=0.0,
                             cloud_monitor_task=None, cloud_recovered=False)
        with pytest.raises((AttributeError, TypeError)):
            snap.cloud_state = "x"  # type: ignore[misc]

    def test_peek_cloud_snapshot_returns_frozen_dataclass(self):
        store = PipelineStateStore()
        snap = store.peek_cloud_snapshot()
        assert isinstance(snap, CloudSnapshot)


# ---------------------------------------------------------------------------
# Scalar setters
# ---------------------------------------------------------------------------

class TestScalarSetters:
    def test_set_pipeline_state(self):
        store = PipelineStateStore()
        _run(store.set_pipeline_state("WATCHING"))
        assert store.peek_pipeline_state() == "WATCHING"

    def test_set_active_system_name(self):
        store = PipelineStateStore()
        _run(store.set_active_system_name("Alexa"))
        assert store.peek_active_system_name() == "Alexa"

    def test_set_detected_lang(self):
        store = PipelineStateStore()
        _run(store.set_detected_lang("fr"))
        assert store.peek_detected_lang() == "fr"

    def test_set_active_room_session(self):
        store = PipelineStateStore()
        _run(store.set_active_room_session("room_123"))
        assert store.peek_active_room_session() == "room_123"

    def test_set_active_room_started_at(self):
        store = PipelineStateStore()
        ts = time.time()
        _run(store.set_active_room_started_at(ts))
        assert store.peek_active_room_started_at() == ts

    def test_set_active_room_participants_copies(self):
        store = PipelineStateStore()
        participants = {"p1", "p2"}
        _run(store.set_active_room_participants(participants))
        participants.add("p3")  # mutate original — store must be unaffected
        assert store.peek_active_room_participants() == {"p1", "p2"}

    def test_peek_active_room_participants_returns_copy(self):
        store = PipelineStateStore()
        _run(store.set_active_room_participants({"p1"}))
        result = store.peek_active_room_participants()
        result.add("p99")  # mutate returned set — store must be unaffected
        assert store.peek_active_room_participants() == {"p1"}

    def test_set_last_face_seen(self):
        store = PipelineStateStore()
        ts = time.time()
        _run(store.set_last_face_seen(ts))
        assert store.peek_last_face_seen() == ts

    def test_set_last_user_speech_at(self):
        store = PipelineStateStore()
        ts = time.time()
        _run(store.set_last_user_speech_at(ts))
        assert store.peek_last_user_speech_at() == ts

    def test_set_last_kairos_at(self):
        store = PipelineStateStore()
        ts = time.time()
        _run(store.set_last_kairos_at(ts))
        assert store.peek_last_kairos_at() == ts

    def test_set_last_silent_update(self):
        store = PipelineStateStore()
        ts = time.time()
        _run(store.set_last_silent_update(ts))
        assert store.peek_last_silent_update() == ts

    def test_set_cloud_monitor_task(self):
        store = PipelineStateStore()
        sentinel = object()
        _run(store.set_cloud_monitor_task(sentinel))
        assert store.peek_cloud_monitor_task() is sentinel


# ---------------------------------------------------------------------------
# Store base class invariants
# ---------------------------------------------------------------------------

class TestStoreBaseInvariants:
    def test_inherits_from_store(self):
        from core.store_base import Store
        assert issubclass(PipelineStateStore, Store)

    def test_has_lock(self):
        import asyncio
        store = PipelineStateStore()
        assert isinstance(store._lock, asyncio.Lock)

    def test_reset_is_sync(self):
        import inspect
        store = PipelineStateStore()
        assert not inspect.iscoroutinefunction(store.reset)
