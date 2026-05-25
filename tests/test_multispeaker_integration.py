"""
Wave 7 Item 24 — multi-speaker integration tests.

Covers the routing/attribution/room-block helpers that are the core of the
multi-speaker feature surface (S39, S88, S111-S115, S3B.1, S3B.4).

Stub-before-import pattern
--------------------------
Windows dev machine crashes when core.voice is imported (OSError 0xc0000139 —
torchaudio DLL not compatible with the local torch build). pipeline.py imports
core.voice at module top, so ANY test that imports pipeline.py must stub
core.voice (and core.audio) into sys.modules BEFORE the import.

Pattern used here:
    import sys, types
    from unittest.mock import MagicMock
    _voice_stub = types.ModuleType('core.voice')
    ...
    sys.modules['core.voice'] = _voice_stub
    sys.modules['core.audio'] = _audio_stub
    from pipeline import _format_multispeaker_transcript, ...

This file replicates this technique so future Wave-style tests can use it as
a reference.
"""
import sys
import time
import types
from unittest.mock import AsyncMock, MagicMock

# ── Stub core.voice and core.audio BEFORE pipeline.py is imported ────────────
# P0.R6.Y D3 cascade: identify + diarize are async; stubs use AsyncMock.
_voice_stub = types.ModuleType("core.voice")
_voice_stub.load_speaker_embedder = MagicMock(return_value=None)
_voice_stub.identify = AsyncMock(return_value=(None, 0.0))
_voice_stub.diarize = AsyncMock(return_value=[])
_voice_stub.get_diarize_stats = MagicMock(return_value={})

_audio_stub = types.ModuleType("core.audio")
for _fn in [
    "record_until_silence", "transcribe", "speak", "speak_stream",
    "listen_and_transcribe", "preload_models", "stop_audio",
    "play_filler", "set_lip_active",
]:
    setattr(_audio_stub, _fn, MagicMock())

if "core.voice" not in sys.modules:
    sys.modules["core.voice"] = _voice_stub
if "core.audio" not in sys.modules:
    sys.modules["core.audio"] = _audio_stub

# ── Now safe to import pipeline helpers ──────────────────────────────────────
from pipeline import (  # noqa: E402
    _format_multispeaker_transcript,
    _user_to_user_heuristic,
    _build_room_block,
)
from core.session_state import SessionSnapshot, VoiceEvidence


# ── Test 1: N=2 speakers — legacy inline format ───────────────────────────────

class TestMultispeakerTranscript:
    def test_two_speakers_legacy_format_preserved(self):
        """N=2 must use legacy [Name]: text format (S3B.4 backward-compat)."""
        brain_text, log_preview, labels = _format_multispeaker_transcript([
            ("Jagan", "What's the plan?"),
            ("Lexi",  "Not sure yet."),
        ])
        assert "[Jagan]: What's the plan?" in brain_text
        assert "[Lexi]: Not sure yet." in brain_text
        assert "Jagan" in log_preview
        assert "Lexi" in log_preview
        assert labels == ["Jagan", "Lexi"]
        # Order preserved
        assert brain_text.index("Jagan") < brain_text.index("Lexi")

    def test_three_speakers_n_speaker_header_rendered(self):
        """N≥3 must use '[N voices simultaneously]' header block (S3B.4)."""
        brain_text, log_preview, labels = _format_multispeaker_transcript([
            ("Jagan", "Yes?"),
            ("Lexi",  "Hi"),
            ("Mike",  "Hello"),
        ])
        assert "3 voices simultaneously" in brain_text
        assert "Jagan" in brain_text
        assert "Lexi" in brain_text
        assert "Mike" in brain_text
        assert len(labels) == 3

    def test_unknown_speaker_gets_numbered_label(self):
        """None name → unknown_N label; numbering is per-utterance."""
        brain_text, log_preview, labels = _format_multispeaker_transcript([
            ("Jagan",  "I heard something."),
            (None,     "Unidentified voice."),
        ])
        assert "unknown_1" in brain_text
        assert "Jagan" in brain_text
        assert "unknown_1" in labels

    def test_single_pair_returns_empty(self):
        """< 2 pairs → empty returns; caller falls back to single-speaker path."""
        brain_text, log_preview, labels = _format_multispeaker_transcript([
            ("Jagan", "Just me."),
        ])
        assert brain_text == ""
        assert log_preview == ""
        assert labels == []


# ── Test 2: User-to-user heuristic ───────────────────────────────────────────

class TestUserToUserHeuristic:
    def test_vocative_to_active_person_returns_user_to_person(self):
        """'Lexi, can you check?' → ('user_to_person', 'Lexi') — brain stays silent."""
        result = _user_to_user_heuristic(
            text="Lexi, can you check this for me?",
            system_name="Kara",
            other_session_names={"Lexi", "Mike"},
        )
        assert result is not None
        assert result[0] == "user_to_person"
        assert result[1] == "Lexi"

    def test_vocative_to_system_name_returns_addressing_ai(self):
        """'Hey Kara, what's the weather?' → ('addressing_ai', 'Kara')."""
        result = _user_to_user_heuristic(
            text="Hey Kara, what's the weather?",
            system_name="Kara",
            other_session_names={"Lexi", "Mike"},
        )
        assert result is not None
        assert result[0] == "addressing_ai"

    def test_subject_mention_without_vocative_returns_none(self):
        """Subject-line mention without comma-vocative → None (classifier runs)."""
        result = _user_to_user_heuristic(
            text="I was talking with Lexi yesterday.",
            system_name="Kara",
            other_session_names={"Lexi", "Mike"},
        )
        assert result is None


# ── Test 3: ROOM block ────────────────────────────────────────────────────────

class TestRoomBlock:
    def _make_snap(self, person_id, person_name, person_type, now, room_session_id="room_1"):
        return SessionSnapshot(
            person_id=person_id, person_name=person_name, person_type=person_type,
            session_type="face", started_at=now - 60, last_face_seen=now - 60,
            last_spoke_at=now - 60, voice_confidence=1.0, evidence=VoiceEvidence(),
            room_session_id=room_session_id, user_turns=0, kairos_clock_reset=True,
            voice_only_origin=False, waiting_for_name=False, voice_face_confirmed=False,
            db_enrolled=False, confidence_tier="", prior_person_type=None,
            dispute_reason=None, disputed_claimed_name=None, dispute_set_at=None,
            disputed_block_count=0, disputed_block_alerted=False, recent_voice_confs=[],
            cached_prefix=None, core_memory=[], tool_repeat_last=None,
            tool_repeat_count=0, recent_attributions=[],
        )

    def test_room_block_names_all_active_sessions(self):
        """Multi-person room with 3 sessions — ROOM block names all 3."""
        now = time.time()
        active_sessions = (
            self._make_snap("jagan_pid", "Jagan", "best_friend", now),
            self._make_snap("lexi_pid", "Lexi", "known", now),
            self._make_snap("mike_pid", "Mike", "stranger", now),
        )
        conversation = {
            "jagan_pid": [{"role": "user", "content": "Hi", "ts": now - 30}],
            "lexi_pid":  [{"role": "user", "content": "Hello", "ts": now - 20}],
            "mike_pid":  [{"role": "user", "content": "Hey", "ts": now - 5}],
        }
        room_block = _build_room_block(
            active_sessions=active_sessions,
            conversation=conversation,
            emotion_agents={},
            room_start_ts=now - 60,
            turn_cap=10,
            now=now,
        )
        assert room_block is not None
        assert "Jagan" in room_block
        assert "Lexi" in room_block
        assert "Mike" in room_block

    def test_room_block_returns_none_for_single_session(self):
        """Single-session → None (backward-compat — SCENE-only path)."""
        now = time.time()
        active_sessions = (
            self._make_snap("jagan_pid", "Jagan", "best_friend", now),
        )
        room_block = _build_room_block(
            active_sessions=active_sessions,
            conversation={"jagan_pid": []},
            emotion_agents={},
            room_start_ts=now - 60,
            now=now,
        )
        assert room_block is None
