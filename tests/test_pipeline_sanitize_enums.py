"""test_pipeline_sanitize_enums — sanitize enums tests (split from test_pipeline.py, P1.A1 SP-1).

Behavior-neutral move: test bodies are verbatim from the original root
test_pipeline.py. `import pipeline` stays lazy inside each test body (stubs are
installed by tests/conftest.py).
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

import asyncio
import sys
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock
import types
import pytest
import numpy as np
import time as _time_mod
import numpy as _np


def test_sanitize_name_plain():
    from pipeline import sanitize_name
    display, safe = sanitize_name("Jagan")
    assert display == "Jagan"
    assert safe == "jagan"


def test_sanitize_name_strips_phrase_prefix_my_name_is():
    from pipeline import sanitize_name
    display, safe = sanitize_name("My name is Jagan")
    assert display == "Jagan"
    assert safe == "jagan"


def test_sanitize_name_strips_phrase_prefix_call_me():
    from pipeline import sanitize_name
    display, safe = sanitize_name("call me Rex")
    assert display == "Rex"
    assert safe == "rex"


def test_sanitize_name_path_traversal_blocked():
    from pipeline import sanitize_name
    display, safe = sanitize_name("../../etc/passwd")
    # safe must contain only [a-z0-9_-]
    import re
    assert re.fullmatch(r"[a-z0-9_\-]+", safe), f"Unsafe id component: {safe!r}"
    assert ".." not in safe
    assert "/" not in safe


def test_sanitize_name_empty_gives_unknown():
    from pipeline import sanitize_name
    display, safe = sanitize_name("")
    assert safe == "unknown"


def test_sanitize_name_unicode_transliterated():
    from pipeline import sanitize_name
    _, safe = sanitize_name("Ångström")
    import re
    assert re.fullmatch(r"[a-z0-9_\-]+", safe), f"Unsafe id component: {safe!r}"


def test_sanitize_name_max_length():
    from pipeline import sanitize_name
    long_name = "A" * 100
    display, safe = sanitize_name(long_name)
    assert len(display) <= 50
    assert len(safe) <= 50


def test_sanitize_name_spaces_become_underscores():
    from pipeline import sanitize_name
    _, safe = sanitize_name("Jean Paul")
    assert " " not in safe


def test_cloudstate_enum_values_exist():
    from pipeline import CloudState
    assert hasattr(CloudState, "ONLINE")
    assert hasattr(CloudState, "SICK")
    assert hasattr(CloudState, "OFFLINE")


def test_cloudstate_initial_is_online():
    import pipeline
    from pipeline import CloudState
    assert pipeline._pipeline_state_store.peek_cloud_state() == CloudState.ONLINE


def test_root_conftest_session_reset_fixture_is_active(request):
    """Guard against future removal of the root-level store-reset autouse fixture.

    Renamed from _reset_session_state_between_tests to
    _reset_pipeline_state_between_tests in P0.6.1 to cover all P0.6 Stores.
    """
    assert "_reset_pipeline_state_between_tests" in request.fixturenames, (
        "Root conftest.py autouse fixture '_reset_pipeline_state_between_tests' is missing — "
        "Store state (SessionStore + P0.6 Stores) leaks between tests without it."
    )


def test_strip_im_contraction_helper_variants():
    """Session 94 Fix #2: the helper strips ``Im`` / ``I'm`` / ``I\u2019m``
    (ASCII apostrophe + Unicode right single quote) prefixes when followed
    by a letter. Whisper's compression drops the name's capital so the
    following letter may be lowercase ('Imlexi' has lowercase 'l').
    Requires capital ``I`` at start to distinguish the first-person
    contraction from mid-sentence words. Accepts the false-positive cost
    on common words like 'Important' — those shouldn't appear as
    extracted_value/tool_args[name] in practice."""
    from pipeline import _strip_im_contraction
    # Canonical live-canary case: Whisper-compressed "I'm Lexi" → "Imlexi".
    assert _strip_im_contraction("Imlexi") == "lexi"
    # Apostrophe preserved — classifier-output form.
    assert _strip_im_contraction("I'mSarah") == "Sarah"
    # Unicode right single quote (U+2019) — some STT backends emit this.
    assert _strip_im_contraction("I\u2019mSarah") == "Sarah"
    # Lowercase initial — NOT a contraction (mid-sentence word); don't strip.
    assert _strip_im_contraction("important") == "important"
    assert _strip_im_contraction("immediate") == "immediate"
    # Empty / None — safe fallback.
    assert _strip_im_contraction("") == ""
    assert _strip_im_contraction(None) == ""
    # "Im" alone (no following letter) — not a contraction match; stay.
    assert _strip_im_contraction("Im") == "Im"
