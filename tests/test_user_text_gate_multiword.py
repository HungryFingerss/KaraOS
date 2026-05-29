"""
P0.3 — _user_text_gate_passes multi-word name behavior tests.

Bug: the v1 remainder check (`_remainder in user_text`) allowed LLM to combine
words from different parts of the utterance. "call me sarah and my friend is
jane" → captured="sarah", remainder="jane" → "jane" in text → ALLOWED "Sarah
Jane" (privilege escalation — LLM fabricated the full name).

Fix (v3): require the full proposed name as a CONTIGUOUS substring of user_text
(`new_value_lower in user_text_lower`).

DOES import pipeline — stubs core.voice and core.audio inline to avoid the
Windows torchaudio DLL crash (OSError 0xc0000139). Same pattern as
tests/test_multispeaker_integration.py and tests/test_dispute_auto_clear.py.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

import sys
import types
from unittest.mock import AsyncMock, MagicMock

import pytest

# ── stubs must be installed BEFORE importing pipeline ────────────────────────
# P0.R6.Y D3 cascade: identify + diarize are async; stubs use AsyncMock.

if "core.voice" not in sys.modules:
    _voice_stub = types.ModuleType("core.voice")
    _voice_stub.load_speaker_embedder = MagicMock(return_value=None)
    _voice_stub.identify = AsyncMock(return_value=(None, 0.0, True))
    _voice_stub.diarize = AsyncMock(return_value=[])
    _voice_stub.get_diarize_stats = MagicMock(return_value={})
    sys.modules["core.voice"] = _voice_stub

if "core.audio" not in sys.modules:
    _audio_stub = types.ModuleType("core.audio")
    for _fn in [
        "record_until_silence", "transcribe", "speak", "speak_stream",
        "listen_and_transcribe", "preload_models", "stop_audio",
        "play_filler", "set_lip_active",
    ]:
        setattr(_audio_stub, _fn, MagicMock())
    sys.modules["core.audio"] = _audio_stub

import pipeline  # noqa: E402  (stubs must precede this)
from pipeline import _user_text_gate_passes  # noqa: E402
from core.config import PERSON_NAME_ASSIGN_PATTERNS, SYSTEM_NAME_ASSIGN_PATTERNS

P = PERSON_NAME_ASSIGN_PATTERNS
S = SYSTEM_NAME_ASSIGN_PATTERNS


# ── single-word baseline — must still pass after v3 fix ──────────────────────

@pytest.mark.parametrize("user_text,new_value,patterns", [
    ("call me sarah", "Sarah", P),
    ("my name is john", "John", P),
    ("i'm alex", "Alex", P),
])
def test_single_word_baseline_passes(user_text, new_value, patterns):
    assert _user_text_gate_passes(user_text, new_value, patterns) is True


# ── legitimate multi-word names — must pass (contiguous in user_text) ─────────

@pytest.mark.parametrize("user_text,new_value,patterns", [
    ("call me sarah jane", "Sarah Jane", P),
    ("my name is mary ann", "Mary Ann", P),
    ("i'm jean paul", "Jean Paul", P),
    ("it's me, sarah jane", "Sarah Jane", P),
    ("people call me jo anne", "Jo Anne", P),
    ("call you sarah jane", "Sarah Jane", S),
    ("your name is sarah jane", "Sarah Jane", S),
    ("call me anna marie", "Anna Marie", P),
    ("my name is david james", "David James", P),
    ("i am sarah jane", "Sarah Jane", P),
])
def test_multiword_legitimate_passes(user_text, new_value, patterns):
    assert _user_text_gate_passes(user_text, new_value, patterns) is True


# ── non-contiguous discriminating cases (v1 allowed; v3 must reject) ─────────

@pytest.mark.parametrize("user_text,new_value,patterns", [
    # The four non-contiguous discriminating cases from the P0.3 spec.
    # v1 buggy fix: _remainder="jane" in user_text → True (WRONG).
    # v3 fix:       "sarah jane" in user_text → False (correct).
    ("call me sarah and my friend is jane", "Sarah Jane", P),
    ("my name is sarah but jane is my sister", "Sarah Jane", P),
    ("i'm sarah and i know jane", "Sarah Jane", P),
    ("call me jean and paul is a nice name", "Jean Paul", P),
])
def test_noncontiguous_discriminating_rejected(user_text, new_value, patterns):
    assert _user_text_gate_passes(user_text, new_value, patterns) is False


# ── other fabrication-rejection cases ────────────────────────────────────────

@pytest.mark.parametrize("user_text,new_value,patterns", [
    # LLM hallucinated an extra word not present in user_text at all
    ("call me sarah", "Sarah Connor", P),
    ("my name is john", "John Smith", P),
    ("i'm sarah", "Sarah Jane", P),
    ("call me anna", "Anna Marie", P),
    # Non-contiguous via a filler word between first and last name
    ("call me sarah okay then", "Sarah Then", P),
    ("my name is jean but paul is my friend", "Jean Paul", P),
])
def test_fabrication_rejected(user_text, new_value, patterns):
    assert _user_text_gate_passes(user_text, new_value, patterns) is False


# ── empty / None user_text ────────────────────────────────────────────────────

def test_empty_user_text_rejected():
    """Empty user_text must be rejected (reject_on_empty_user_text=True default)."""
    assert _user_text_gate_passes("", "Sarah Jane", P) is False


def test_none_user_text_rejected():
    """None user_text must be rejected (treated as empty)."""
    assert _user_text_gate_passes(None, "Sarah Jane", P) is False
