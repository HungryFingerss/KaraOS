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
        "_cache_store",            # P0.6.5
        "_pipeline_state_store",   # P0.6.6
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
    except Exception as _e:
        print(f"[conftest] store reset failed: {_e!r}")
    yield
