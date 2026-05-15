"""
P0.3 — _user_text_gate_passes structural invariants (fast-tier, DLL-safe).

Reads pipeline.py as raw text and inspects the function body for:
  Invariant 1: _nfkc_lower called ≥3 times (all three inputs normalized)
  Invariant 2: "_nv_lower in _lt" present (contiguous substring check)
  Invariant 3: "_remainder" NOT present (v1 buggy variable removed)

Plus 2 behavioral detector self-tests (stub-before-import pattern):
  Self-test 1: discriminating non-contiguous case is rejected
  Self-test 2: legitimate multi-word case is accepted
"""
import ast
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_ROOT = Path(__file__).resolve().parent.parent
PIPELINE_PATH = _ROOT / "pipeline.py"


# ── helpers ───────────────────────────────────────────────────────────────────

def _get_gate_source() -> str:
    """Extract the source lines of _user_text_gate_passes from pipeline.py."""
    source = PIPELINE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_user_text_gate_passes":
            lines = source.splitlines()
            # Extract from function start to end (lineno is 1-based)
            start = node.lineno - 1
            end = node.end_lineno
            return "\n".join(lines[start:end])
    raise AssertionError("_user_text_gate_passes not found in pipeline.py")


# ── Invariant 1: NFKC applied to all three inputs ────────────────────────────

def test_nfkc_lower_called_at_least_3_times_in_gate():
    """All three inputs (user_text, new_value, captured) must use _nfkc_lower."""
    body = _get_gate_source()
    count = body.count("_nfkc_lower(")
    assert count >= 3, (
        f"Expected _nfkc_lower() called ≥3 times in _user_text_gate_passes, "
        f"but found {count} calls. "
        f"P0.3 fix requires NFKC normalization on user_text, new_value, AND captured."
    )


# ── Invariant 2: contiguous substring check present ──────────────────────────

def test_contiguous_substring_check_present_in_gate():
    """The v3 fix must use 'in _lt' for the full proposed name (contiguous check)."""
    body = _get_gate_source()
    assert "_nv_lower in _lt" in body, (
        "_nv_lower in _lt not found in _user_text_gate_passes body. "
        "P0.3 fix requires a contiguous substring check to prevent non-contiguous "
        "word combinations ('call me sarah ... is jane' ≠ 'Sarah Jane')."
    )


# ── Invariant 3: _remainder variable removed (v1 buggy fix gone) ─────────────

def test_remainder_variable_not_in_gate():
    """The v1 buggy _remainder variable must not appear in the function body."""
    body = _get_gate_source()
    # Allow "_remainder" only if it's in a comment (docstring context)
    # Strip comments and check code lines only
    code_lines = [
        ln for ln in body.splitlines()
        if not ln.strip().startswith("#")
    ]
    code_body = "\n".join(code_lines)
    assert "_remainder" not in code_body, (
        "_remainder variable found in _user_text_gate_passes body. "
        "P0.3 fix should have removed the v1 buggy remainder check "
        "('_remainder in _lt' allowed non-contiguous word combinations)."
    )


# ── Behavioral self-tests (stubs installed inline) ───────────────────────────

if "core.voice" not in sys.modules:
    _voice_stub = types.ModuleType("core.voice")
    _voice_stub.load_speaker_embedder = MagicMock(return_value=None)
    _voice_stub.identify = MagicMock(return_value=(None, 0.0))
    _voice_stub.diarize = MagicMock(return_value=[])
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

from pipeline import _user_text_gate_passes  # noqa: E402
from core.config import PERSON_NAME_ASSIGN_PATTERNS  # noqa: E402

P = PERSON_NAME_ASSIGN_PATTERNS


def test_discriminating_noncontiguous_case_rejected():
    """
    The key P0.3 discriminating case: "sarah" and "jane" appear in the utterance
    but not contiguously as "sarah jane" — must be REJECTED.
    v1 allowed this (remainder "jane" in text); v3 must reject it.
    """
    result = _user_text_gate_passes(
        "call me sarah and my friend is jane", "Sarah Jane", P
    )
    assert result is False, (
        "Non-contiguous case 'call me sarah and my friend is jane' → 'Sarah Jane' "
        "must be REJECTED. The v1 buggy fix allowed this; v3 contiguous check must not."
    )


def test_legitimate_multiword_name_accepted():
    """
    Legitimate multi-word name: "Sarah Jane" appears contiguously in user_text.
    Must be ACCEPTED.
    """
    result = _user_text_gate_passes(
        "call me sarah jane", "Sarah Jane", P
    )
    assert result is True, (
        "Legitimate multi-word 'call me sarah jane' → 'Sarah Jane' must be ACCEPTED. "
        "The full name appears as a contiguous substring."
    )
