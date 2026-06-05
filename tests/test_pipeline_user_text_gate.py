"""test_pipeline_user_text_gate — user text gate tests (split from test_pipeline.py, P1.A1 SP-1).

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


def test_user_text_gate_passes_accepts_capture_match():
    """Session 73: gate passes when the assignment phrase captures a name
    that equals new_value. 'call you Kara' → captures 'kara' → matches."""
    from pipeline import _user_text_gate_passes
    from core.config import SYSTEM_NAME_ASSIGN_PATTERNS
    assert _user_text_gate_passes(
        "I want to call you Kara", "Kara", SYSTEM_NAME_ASSIGN_PATTERNS,
    ) is True


def test_user_text_gate_rejects_detroit_cameo():
    """Bug G1 (2026-04-22): the exact Detroit-rename scenario.
    'do you know the game called Detroit' has 'Detroit' in the turn AND has
    the word 'called', but 'called' is not in an assignment phrase directed
    at the AI. Old OR-gate accepted; new capture-group gate must reject."""
    from pipeline import _user_text_gate_passes
    from core.config import SYSTEM_NAME_ASSIGN_PATTERNS
    assert _user_text_gate_passes(
        "do you know the game called Detroit? I'm playing it",
        "Detroit",
        SYSTEM_NAME_ASSIGN_PATTERNS,
    ) is False, (
        "the exact Detroit-rename failure from 2026-04-22 must now be blocked"
    )


def test_user_text_gate_rejects_capture_wrong_name():
    """Session 73: pattern matches BUT capture is a different name than
    new_value. 'call you Kara' with new_value='Sarah' → reject. The LLM
    sometimes proposes a name that doesn't match what the user actually said."""
    from pipeline import _user_text_gate_passes
    from core.config import SYSTEM_NAME_ASSIGN_PATTERNS
    assert _user_text_gate_passes(
        "call you Kara", "Sarah", SYSTEM_NAME_ASSIGN_PATTERNS,
    ) is False


def test_user_text_gate_denial_mode_accepts_any_match():
    """Session 73 / Bug G3: denial-signal mode (new_value=None) — pattern
    match alone is sufficient. 'I'm not Jagan' triggers, no name-verify."""
    from pipeline import _user_text_gate_passes
    from core.config import IDENTITY_DENIAL_PATTERNS
    assert _user_text_gate_passes(
        "I'm not Jagan, I told you", None, IDENTITY_DENIAL_PATTERNS,
    ) is True


def test_user_text_gate_denial_mode_rejects_benign_question():
    """Bug G3: 'who are you talking to?' (the exact live-run trigger) must
    NOT match any denial pattern. This was the dispute-flip silent bug."""
    from pipeline import _user_text_gate_passes
    from core.config import IDENTITY_DENIAL_PATTERNS
    assert _user_text_gate_passes(
        "Hey, who are you talking to?", None, IDENTITY_DENIAL_PATTERNS,
    ) is False, (
        "the exact question that wrongly triggered dispute in 2026-04-22 "
        "must not match any denial pattern"
    )


def test_user_text_gate_accepts_multi_word_name():
    """Session 73 post-review Critical #3: 'Call me Sarah Jane' has (\\w+) capture
    = 'sarah' but the LLM proposes 'Sarah Jane' as new_value. The gate must
    accept via the prefix-match path because 'jane' also appears in user_text."""
    from pipeline import _user_text_gate_passes
    from core.config import PERSON_NAME_ASSIGN_PATTERNS
    assert _user_text_gate_passes(
        "call me Sarah Jane, please", "Sarah Jane", PERSON_NAME_ASSIGN_PATTERNS,
    ) is True


def test_user_text_gate_accepts_three_word_name():
    """Critical #3: 'my name is Mary Ann Smith' → capture 'mary', proposal
    'Mary Ann Smith' → prefix match, remainder 'ann smith' in user_text → accept."""
    from pipeline import _user_text_gate_passes
    from core.config import PERSON_NAME_ASSIGN_PATTERNS
    assert _user_text_gate_passes(
        "my name is Mary Ann Smith", "Mary Ann Smith", PERSON_NAME_ASSIGN_PATTERNS,
    ) is True


def test_user_text_gate_rejects_fabricated_multi_word_suffix():
    """Critical #3 safety: prefix-match must NOT open the gate to an LLM
    fabricating extra words the user never said. 'Call me Sarah' +
    proposal 'Sarah Jones' — 'jones' NOT in user_text → reject."""
    from pipeline import _user_text_gate_passes
    from core.config import PERSON_NAME_ASSIGN_PATTERNS
    assert _user_text_gate_passes(
        "call me Sarah, it's short for something", "Sarah Jones",
        PERSON_NAME_ASSIGN_PATTERNS,
    ) is False, (
        "prefix-match must still require the full multi-word name to appear "
        "in user_text — otherwise it's a fabrication bypass"
    )


def test_user_text_gate_accepts_system_multi_word_name():
    """Critical #3 parity: same accept path works for system names
    (SYSTEM_NAME_ASSIGN_PATTERNS). 'Call you Baby Yoda' → captured 'baby',
    proposal 'Baby Yoda' → prefix match + remainder 'yoda' in turn → accept."""
    from pipeline import _user_text_gate_passes
    from core.config import SYSTEM_NAME_ASSIGN_PATTERNS
    assert _user_text_gate_passes(
        "I want to call you Baby Yoda", "Baby Yoda", SYSTEM_NAME_ASSIGN_PATTERNS,
    ) is True


def test_user_text_gate_rejects_empty_user_text_by_default():
    """Option A (Session 73): empty user_text means the LLM is acting
    unilaterally (e.g. via KAIROS proactive path). Mutation tools must NOT
    silently succeed on empty — default REJECT. Callers who want the old
    'allow on empty' behavior must opt in explicitly."""
    from pipeline import _user_text_gate_passes
    from core.config import SYSTEM_NAME_ASSIGN_PATTERNS
    assert _user_text_gate_passes("", "Kara", SYSTEM_NAME_ASSIGN_PATTERNS) is False
    assert _user_text_gate_passes(None, "Kara", SYSTEM_NAME_ASSIGN_PATTERNS) is False
    assert _user_text_gate_passes("   ", "Kara", SYSTEM_NAME_ASSIGN_PATTERNS) is False


def test_user_text_gate_allows_empty_when_explicitly_opted_in():
    """Option A escape hatch: callers that genuinely need 'allow on empty'
    (e.g. debug tools, batch fixtures) can flip the flag. The default-safe
    contract is preserved."""
    from pipeline import _user_text_gate_passes
    from core.config import SYSTEM_NAME_ASSIGN_PATTERNS
    assert _user_text_gate_passes(
        "", "Kara", SYSTEM_NAME_ASSIGN_PATTERNS,
        reject_on_empty_user_text=False,
    ) is True
