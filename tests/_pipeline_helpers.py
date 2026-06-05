"""Shared test-data builders for the split test_pipeline_<concern>.py files (P1.A1 SP-1).

Verbatim from the original root test_pipeline.py. `import pipeline` stays lazy
inside each helper body (the stub-before-import discipline; stubs are installed
by tests/conftest.py). Includes a few orphaned-but-preserved helpers (behavior-neutral move: relocate dead code, never delete it).
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


def _make_shutdown_session():
    """Minimal best_friend session dict for shutdown loop tests (only best_friend can shutdown)."""
    import time as _t
    return {
        "person_id":        "p_sd",
        "person_name":      "Jagan",
        "person_type":      "best_friend",
        "session_type":     "face",
        "last_face_seen":   _t.time(),
        "last_spoke_at":    _t.time(),
        "voice_confidence": 1.0,
        "started_at":       _t.time(),
    }


class _FakeSegment:
    """Mimics pyannote.core.Segment — only .start / .end float fields."""
    __slots__ = ("start", "end")
    def __init__(self, start: float, end: float):
        self.start, self.end = float(start), float(end)


class _FakeAnnotation:
    """Mimics pyannote.core.Annotation — only itertracks(yield_label=True)
    which is what ``_diarize_pyannote`` calls. Each track is a
    (Segment, track_id, speaker_label) tuple per pyannote's public API."""
    def __init__(self, tracks: list[tuple[_FakeSegment, str, str]]):
        self._tracks = tracks
    def itertracks(self, yield_label: bool = False):
        if not yield_label:
            for seg, tid, _ in self._tracks:
                yield seg, tid
        else:
            for seg, tid, label in self._tracks:
                yield seg, tid, label


def _fake_pipeline(return_annotation: _FakeAnnotation):
    """Build a callable that mimics pyannote's Pipeline — accepts the
    in-memory waveform dict (ignored in tests) and returns a preset
    Annotation. Only the __call__ surface is used by our code."""
    class _FakePipeline:
        def __call__(self, _waveform_dict):
            return return_annotation
    return _FakePipeline()


def _reset_tool_repeat_guard(sess_dict, pid):
    """Simulate the per-turn reset of the tool-repeat guard so a test can call
    the same tool twice without tripping the loop guard at pipeline.py:1432."""
    if pid in sess_dict:
        sess_dict[pid].pop("_tool_repeat_last",  None)
        sess_dict[pid].pop("_tool_repeat_count", None)


def _s3b1_sess(pid, name, ptype="known"):
    """Minimal SessionSnapshot for _build_room_block / _build_scene_block tests."""
    import time as _t
    from core.session_state import SessionSnapshot, VoiceEvidence
    now = _t.time()
    return SessionSnapshot(
        person_id=pid, person_name=name, person_type=ptype,
        session_type="face", started_at=now, last_face_seen=now,
        last_spoke_at=now, voice_confidence=1.0, evidence=VoiceEvidence(),
        room_session_id="room_test", user_turns=0, kairos_clock_reset=True,
        voice_only_origin=False, waiting_for_name=False, voice_face_confirmed=False,
        db_enrolled=False, confidence_tier="", prior_person_type=None,
        dispute_reason=None, disputed_claimed_name=None, dispute_set_at=None, dispute_set_at_monotonic=None,
        disputed_block_count=0, disputed_block_alerted=False, recent_voice_confs=[],
        cached_prefix=None, core_memory=[], tool_repeat_last=None,
        tool_repeat_count=0, recent_attributions=[],
    )
