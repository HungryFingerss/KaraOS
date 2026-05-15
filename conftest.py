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
def _reset_session_state_between_tests():
    """Reset SessionStore between every test — prevents pid-collision failures in test_pipeline.py.

    Mirrors tests/conftest.py's version. No _active_sessions.clear() — that global is gone (P0.7).
    """
    try:
        from core.session_state import SessionStore
        import pipeline as _pipeline
        if hasattr(_pipeline, "_session_store"):
            _pipeline._session_store = SessionStore()
    except Exception as _e:
        print(f"[conftest] session-store reset failed: {_e!r}")
    yield
