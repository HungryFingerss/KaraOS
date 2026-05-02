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
