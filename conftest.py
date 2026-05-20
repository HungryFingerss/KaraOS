"""Repository-level conftest.

Currently provides one mechanism: opt-in flag for tests that depend on a
live Together.ai / Ollama call. By default `pytest` skips them so a
network-flaky API doesn't break the suite. Run them on demand with
`pytest --run-network`.

Authorized in info.md (2026-04-28): "lets skip the two together ai call
tests, lets only run them when needed".
"""
from __future__ import annotations

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--run-network",
        action="store_true",
        default=False,
        help="Include tests marked @pytest.mark.network (live Together.ai / Ollama).",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-network"):
        return
    skip_marker = pytest.mark.skip(reason="needs --run-network flag (live Together.ai / Ollama)")
    for item in items:
        if "network" in item.keywords:
            item.add_marker(skip_marker)


@pytest.fixture(autouse=True)
def _reset_pipeline_state_between_tests():
    """Reset all Stores between every test — prevents state leakage.

    P0.7: resets _session_store (SessionStore).
    P0.6: resets every P0.6 Store via .reset(); hasattr guards make this
    forward-compatible as sub-PRs land new Stores.

    _STORE_NAMES is the canonical list — tests/test_p06_store_invariants.py
    TestAutouseFixtureCoversEveryStore verifies this list stays in sync with
    core/*_store.py definitions (auditor M2 fix).
    """
    _STORE_NAMES = (
        "_presence_store",         # P0.6.2
        "_track_store",            # P0.6.2
        "_conversation_store",     # P0.6.3
        "_voice_gallery_store",    # P0.6.4
        "_per_person_agent_store", # P0.6.4
        "_identity_hints_store",   # P0.6.5
        "_query_embedding_store",  # P0.6.5
        "_scene_block_store",      # P0.6.5
        "_classifier_cache_store", # P0.6.5
        "_pipeline_state_store",   # P0.6.6
        "_vision_frame_store",     # P0.6.7v2
        "_anti_spoof_rejection_store",  # P0.S1 MED 5
    )
    try:
        from core.session_state import SessionStore
        import pipeline as _pipeline
        # P0.7 store — replaced directly (not via .reset()) to ensure a fresh lock.
        if hasattr(_pipeline, "_session_store"):
            _pipeline._session_store = SessionStore()
        # P0.6 stores — reset via .reset() (sync, no event loop needed).
        for _sname in _STORE_NAMES:
            if hasattr(_pipeline, _sname):
                getattr(_pipeline, _sname).reset()
        # P0.6.6: replace _pipeline_state_store with a fresh production-shape
        # instance — restores initial_pipeline_state=WATCHING + initial_cloud_state=ONLINE
        # defaults that reset() alone would wipe (reset() is a sync arg-less
        # contract so it can't carry the initials).
        if (hasattr(_pipeline, "PipelineStateStore")
                and hasattr(_pipeline, "PipelineState")
                and hasattr(_pipeline, "CloudState")):
            _pipeline._pipeline_state_store = _pipeline.PipelineStateStore(
                initial_pipeline_state=_pipeline.PipelineState.WATCHING,
                initial_cloud_state=_pipeline.CloudState.ONLINE,
            )
        # P0.S7.D-D — re-init RoomOrchestrator with fresh stores. The class
        # composes over the 6 dependencies; some (face_db, brain_orchestrator)
        # may be None in test contexts that don't touch those subsystems.
        # The class __init__ stores all deps without asserting; per-method
        # None checks handle the gaps (Plan v2 §4 refined 3-layer defense).
        if hasattr(_pipeline, "RoomOrchestrator"):
            _pipeline._room_orchestrator = _pipeline.RoomOrchestrator(
                session_store=_pipeline._session_store,
                pipeline_state_store=_pipeline._pipeline_state_store,
                face_db=getattr(_pipeline, "_face_db_ref", None),
                brain_orchestrator=getattr(_pipeline, "_brain_orchestrator", None),
                conversation_store=_pipeline._conversation_store,
                emotion_agents=getattr(_pipeline, "_emotion_agents", {}),
            )
    except Exception as _e:
        print(f"[conftest] store reset failed: {_e!r}")
    yield
