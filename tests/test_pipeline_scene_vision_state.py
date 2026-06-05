"""test_pipeline_scene_vision_state — scene vision state tests (split from test_pipeline.py, P1.A1 SP-1).

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


def test_vision_report_none_when_no_detections():
    """Vision report string is 'none' when det_count_bv == 0."""
    import asyncio, pipeline, time
    asyncio.run(pipeline._presence_store.upsert_face_recognition("p1", "Jagan", 0.9, time.time()))
    asyncio.run(pipeline._track_store.mark_unrecognized(42, time.time()))
    _det_count_bv = 0
    _vis_report_now = "none" if _det_count_bv == 0 else "other"
    assert _vis_report_now == "none"


def test_vision_report_includes_recognized_and_unrecognized():
    """Vision report shows recognized name + 'unrecognized' when both present and fresh."""
    import asyncio, pipeline, time
    from core.config import VOICE_ROUTING_FACE_STALE_SECS
    t_now = time.time()
    asyncio.run(pipeline._presence_store.upsert_face_recognition("p1", "Jagan", 0.9, t_now - 0.5))
    asyncio.run(pipeline._track_store.mark_unrecognized(42, t_now - 0.5))
    _det_count_bv = 2
    _now_vr  = time.time()
    _rnames  = sorted(
        snap.name for snap in pipeline._presence_store.peek_all_snapshots()
        if _now_vr - snap.last_seen < VOICE_ROUTING_FACE_STALE_SECS
    )
    _unrec_n = sum(
        1 for tid in pipeline._track_store.peek_active_unrecognized()
        if _now_vr - pipeline._track_store.peek_last_seen(tid) < VOICE_ROUTING_FACE_STALE_SECS
    )
    _vr_parts = list(_rnames)
    if _unrec_n == 1:
        _vr_parts.append("unrecognized")
    _vis_report = ", ".join(_vr_parts) if _vr_parts else "none"
    assert "jagan" in _vis_report.lower()
    assert "unrecognized" in _vis_report


def test_vision_heartbeat_interval_is_30s():
    """Both heartbeat locations must use a 30-second interval, not 5 seconds."""
    import inspect
    import pipeline
    src = inspect.getsource(pipeline)
    # Find heartbeat interval comparisons — there should be no 5.0 threshold
    # (both locations converted to 30.0)
    import re
    # Match lines like `>= 5.0` or `>= 5` near _vision_last_heartbeat
    hits_5s = re.findall(r"_vision_last_heartbeat.*?>=\s*5\.0", src)
    assert len(hits_5s) == 0, \
        f"Found heartbeat still using 5.0s interval: {hits_5s}"
    # Confirm 30.0 appears at least twice (one per location)
    hits_30s = re.findall(r"_vision_last_heartbeat.*?>=\s*30\.0", src)
    assert len(hits_30s) >= 2, \
        f"Expected 2 heartbeat locations using 30.0s, found {len(hits_30s)}"


def test_vision_heartbeat_skips_identical_state(capsys):
    """Heartbeat must not print when content is identical to the previous print."""
    import pipeline

    # Simulate both heartbeat locations: same state key → no second print
    _vision_last_heartbeat_state = ""

    def _maybe_print(state_key: str, msg: str) -> str:
        nonlocal _vision_last_heartbeat_state
        if state_key != _vision_last_heartbeat_state:
            _vision_last_heartbeat_state = state_key
            print(msg)
        return _vision_last_heartbeat_state

    # First call with "WATCHING|Jagan" → should print
    _maybe_print("WATCHING|Jagan", "[Vision] Watching — Jagan in frame")
    # Second call with same key → should NOT print
    _maybe_print("WATCHING|Jagan", "[Vision] Watching — Jagan in frame")
    # Third call with different key → should print
    _maybe_print("WATCHING|none", "[Vision] Watching — no face")

    captured = capsys.readouterr()
    lines = [l for l in captured.out.splitlines() if "[Vision] Watching" in l]
    assert len(lines) == 2, \
        f"Expected 2 heartbeat prints (first + state-change), got {len(lines)}: {lines}"


def test_persons_in_frame_updated_for_voice_match():
    """pipeline source must call upsert_voice_recognition for voice-matched persons."""
    import inspect, pipeline
    src = inspect.getsource(pipeline)
    assert "upsert_voice_recognition(" in src, \
        "Voice-identified entries must call _presence_store.upsert_voice_recognition"


def test_scene_block_replaces_room_roster():
    """SCENE block is built every turn; old stranger-addendum 'Room:' roster is removed."""
    import inspect, pipeline
    src = inspect.getsource(pipeline)
    # SCENE block is built in conversation_turn()
    assert "_build_scene_block(" in src, \
        "_build_scene_block must be called in conversation_turn"
    assert "scene_block=" in src, \
        "scene_block must be passed to ask()/ask_stream()"
    # Old stranger-addendum room roster deleted (covered by SCENE block now)
    assert '"Room: "' not in src and "'Room: '" not in src, \
        "Old stranger-addendum Room: roster must be removed — SCENE block covers it"


@pytest.mark.asyncio
async def test_in_session_history_trimmed_at_limit():
    """In-session history accumulation must not exceed CONVERSATION_HISTORY_LIMIT turns."""
    import pipeline
    from pipeline import conversation_turn, CloudState
    from core.config import CONVERSATION_HISTORY_LIMIT

    orig_cloud    = pipeline._pipeline_state_store.peek_cloud_state()
    orig_brain    = pipeline._brain_orchestrator
    orig_lang     = pipeline._pipeline_state_store.peek_detected_lang()
    orig_sysname  = pipeline._pipeline_state_store.peek_active_system_name()
    orig_shutdown = pipeline._shutdown_event

    # Pre-populate history at exactly the limit (simulates loaded DB history)
    pre_history = []
    for i in range(CONVERSATION_HISTORY_LIMIT):
        pre_history.append({"role": "user",      "content": f"user turn {i}"})
        pre_history.append({"role": "assistant",  "content": f"assistant turn {i}"})

    await pipeline._session_store.open_session("p1", "Jagan", "known", "face", now=__import__("time").time())
    await pipeline._conversation_store.set_history("p1", list(pre_history))
    await pipeline._pipeline_state_store.recover_online_no_flag()
    pipeline._per_person_agent_store.reset()
    pipeline._brain_orchestrator    = None
    await pipeline._pipeline_state_store.set_detected_lang("en")
    await pipeline._pipeline_state_store.set_active_system_name("Kara")
    pipeline._shutdown_event        = asyncio.Event()

    async def fake_stream(*a, **kw):
        yield ("text", "Great question, here is the answer.")

    async def fake_speak_stream(sentences, **kw):
        async for _ in sentences:
            pass

    try:
        with patch("pipeline.ask_stream",      new=fake_stream), \
             patch("pipeline.speak_stream",    new=fake_speak_stream), \
             patch("pipeline._set_state"), \
             patch("pipeline.play_filler"), \
             patch("pipeline.autocompact_history",
                   new=AsyncMock(side_effect=lambda h, *a, **kw: h)):
            await conversation_turn("tell me something", "p1", "Jagan", db=None)

        hist = pipeline._conversation_store.peek_history("p1")
        n_turns = len(hist) // 2
        assert n_turns <= CONVERSATION_HISTORY_LIMIT, \
            f"In-session history grew to {n_turns} turns, exceeding limit of {CONVERSATION_HISTORY_LIMIT}"
    finally:
        await pipeline._pipeline_state_store.set_cloud_state(orig_cloud)
        pipeline._brain_orchestrator    = orig_brain
        await pipeline._pipeline_state_store.set_detected_lang(orig_lang)
        await pipeline._pipeline_state_store.set_active_system_name(orig_sysname)
        pipeline._shutdown_event        = orig_shutdown


def test_in_session_history_cap_in_source():
    """pipeline.py must trim history to CONVERSATION_HISTORY_LIMIT * 2 messages."""
    import inspect, pipeline
    src = inspect.getsource(pipeline)
    assert "CONVERSATION_HISTORY_LIMIT * 2" in src, \
        "pipeline must enforce in-session history cap using CONVERSATION_HISTORY_LIMIT"


def test_temporal_buffer_pool_depth_returns_zero_for_unseen_track():
    """#8: pool_depth() returns 0 for a track that hasn't been pooled yet."""
    from core.vision import TemporalEmbeddingBuffer
    buf = TemporalEmbeddingBuffer(max_frames=5)
    assert buf.pool_depth(99) == 0


def test_temporal_buffer_pool_depth_grows_with_each_frame():
    """#8: pool_depth() increments after each add_and_pool call, up to max_frames."""
    import numpy as np
    from core.vision import TemporalEmbeddingBuffer
    buf = TemporalEmbeddingBuffer(max_frames=5)
    emb = np.random.rand(512).astype(np.float32)
    emb /= np.linalg.norm(emb)
    bbox = (0, 0, 64, 64)
    buf.add_and_pool(bbox, emb, track_id=7)
    assert buf.pool_depth(7) == 1
    buf.add_and_pool(bbox, emb, track_id=7)
    assert buf.pool_depth(7) == 2
    for _ in range(10):
        buf.add_and_pool(bbox, emb, track_id=7)
    assert buf.pool_depth(7) == 5  # capped at max_frames


def test_pool_size_gate_raises_threshold_for_shallow_pool():
    """#8: effective threshold increments by 0.05 when pool < 3 frames deep."""
    from core.config import RECOGNITION_THRESHOLD
    from core.vision import adaptive_threshold, TemporalEmbeddingBuffer
    import numpy as np

    buf = TemporalEmbeddingBuffer(max_frames=5)
    emb = np.random.rand(512).astype(np.float32)
    emb /= np.linalg.norm(emb)
    buf.add_and_pool((0, 0, 64, 64), emb, track_id=3)  # pool depth = 1

    quality = 0.8
    base_thresh = adaptive_threshold(quality, RECOGNITION_THRESHOLD)
    # Pool-size gate: depth < 3 → add 0.05
    if buf.pool_depth(3) < 3:
        effective = base_thresh + 0.05
    else:
        effective = base_thresh
    assert effective == base_thresh + 0.05


def test_pool_size_gate_no_penalty_for_deep_pool():
    """#8: No threshold penalty once pool reaches 3+ frames."""
    from core.config import RECOGNITION_THRESHOLD
    from core.vision import adaptive_threshold, TemporalEmbeddingBuffer
    import numpy as np

    buf = TemporalEmbeddingBuffer(max_frames=5)
    emb = np.random.rand(512).astype(np.float32)
    emb /= np.linalg.norm(emb)
    for _ in range(4):
        buf.add_and_pool((0, 0, 64, 64), emb, track_id=5)

    quality = 0.8
    base_thresh = adaptive_threshold(quality, RECOGNITION_THRESHOLD)
    if buf.pool_depth(5) < 3:
        effective = base_thresh + 0.05
    else:
        effective = base_thresh
    assert effective == base_thresh  # no penalty


def test_single_camera_reader_in_pipeline():
    """#10: After run() starts, camera.read() must appear exactly once (background loop)."""
    import re
    src = open("pipeline.py").read()
    # Count synchronous camera.read() calls outside comments (background loop uses run_in_executor)
    direct_reads = [
        ln for ln in src.splitlines()
        if re.search(r'camera\.read\(\)', ln) and not ln.strip().startswith('#')
    ]
    # Only the warmup loop should remain (background loop uses run_in_executor not camera.read())
    non_executor_reads = [ln for ln in direct_reads if 'run_in_executor' not in ln]
    assert len(non_executor_reads) == 1, (
        f"Expected exactly 1 direct camera.read() (warmup only); found {len(non_executor_reads)}:\n"
        + "\n".join(non_executor_reads)
    )


def test_latest_frame_time_tracks_freshness():
    """#10: VisionFrameStore frame_time must be a float initialized to 0.0."""
    import pipeline
    assert isinstance(pipeline._vision_frame_store.peek_frame_time(), float)


def test_stale_frame_treated_as_none():
    """#10: When the stored frame_time is old, peek_frame_if_fresh returns None."""
    import pipeline, time, asyncio
    asyncio.run(pipeline._vision_frame_store.set_frame(object(), time.monotonic() - 10.0))
    frame = pipeline._vision_frame_store.peek_frame_if_fresh(0.5, time.monotonic())
    assert frame is None


def test_effective_switch_threshold_strong_profile():
    """#16: gallery size >= 5 → threshold 0.40."""
    from pipeline import _effective_switch_threshold
    assert _effective_switch_threshold("p1", {"p1": 5})  == 0.40
    assert _effective_switch_threshold("p1", {"p1": 10}) == 0.40


def test_effective_switch_threshold_weak_profile():
    """#16: gallery size < 5 → threshold 0.55."""
    from pipeline import _effective_switch_threshold
    assert _effective_switch_threshold("p1", {"p1": 4})  == 0.55
    assert _effective_switch_threshold("p1", {"p1": 0})  == 0.55
    assert _effective_switch_threshold("p1", {})          == 0.55


def test_count_scene_candidates_excludes_stale_tracks():
    """#16: _count_scene_candidates ignores tracks older than VOICE_ROUTING_FACE_STALE_SECS."""
    from pipeline import _count_scene_candidates
    from core.config import VOICE_ROUTING_FACE_STALE_SECS
    import time
    now   = time.time()
    stale = now - (VOICE_ROUTING_FACE_STALE_SECS + 1.0)
    count = _count_scene_candidates({}, {42: stale}, now)
    assert count == 0


def test_count_scene_candidates_counts_fresh_tracks():
    """#16: fresh unrecognized track is counted as a scene candidate."""
    from pipeline import _count_scene_candidates
    import time
    now = time.time()
    count = _count_scene_candidates({}, {42: now}, now)
    assert count == 1


def test_scene_block_visible_person_speaker():
    """Speaker in persons_in_frame → listed as 'speaking now'."""
    import pipeline as _pl
    from core.session_state import SessionSnapshot, VoiceEvidence
    now = 1000.0
    persons = {"p1": {"name": "Jagan", "last_seen": now - 1, "conf": 0.9}}
    sessions = (SessionSnapshot(
        person_id="p1", person_name="Jagan", person_type="known",
        session_type="face", started_at=now - 60, last_face_seen=now - 1,
        last_spoke_at=now, voice_confidence=1.0, evidence=VoiceEvidence(),
        room_session_id=None, user_turns=0, kairos_clock_reset=True,
        voice_only_origin=False, waiting_for_name=False, voice_face_confirmed=False,
        db_enrolled=False, confidence_tier="", prior_person_type=None,
        dispute_reason=None, disputed_claimed_name=None, dispute_set_at=None, dispute_set_at_monotonic=None,
        disputed_block_count=0, disputed_block_alerted=False, recent_voice_confs=[],
        cached_prefix=None, core_memory=[], tool_repeat_last=None,
        tool_repeat_count=0, recent_attributions=[],
    ),)
    result = _pl._build_scene_block("p1", now, sessions, persons, {}, "p1")
    assert "Jagan (best friend) — speaking now" in result
    assert "<<<SCENE" in result
    assert "<<<END SCENE>>>" in result


def test_scene_block_visible_person_silent():
    """Non-speaker in persons_in_frame → listed as silent."""
    import pipeline as _pl
    from core.session_state import SessionSnapshot, VoiceEvidence
    now = 1000.0
    persons = {"p2": {"name": "Priya", "last_seen": now - 1, "conf": 0.85}}
    sessions = (SessionSnapshot(
        person_id="p2", person_name="Priya", person_type="known",
        session_type="face", started_at=now - 60, last_face_seen=now - 1,
        last_spoke_at=now, voice_confidence=0.85, evidence=VoiceEvidence(),
        room_session_id=None, user_turns=0, kairos_clock_reset=True,
        voice_only_origin=False, waiting_for_name=False, voice_face_confirmed=False,
        db_enrolled=False, confidence_tier="", prior_person_type=None,
        dispute_reason=None, disputed_claimed_name=None, dispute_set_at=None, dispute_set_at_monotonic=None,
        disputed_block_count=0, disputed_block_alerted=False, recent_voice_confs=[],
        cached_prefix=None, core_memory=[], tool_repeat_last=None,
        tool_repeat_count=0, recent_attributions=[],
    ),)
    result = _pl._build_scene_block("p1", now, sessions, persons, {}, "bf1")
    assert "Priya (known) — silent" in result


def test_scene_block_unrecognized_faces_counted():
    """Active unrecognized tracks → counted, never named."""
    import pipeline as _pl
    now = 1000.0
    unrec = {101: now - 1, 102: now - 2}
    result = _pl._build_scene_block(None, now, {}, {}, unrec, None)
    assert "2 unrecognized faces (not greeted yet)" in result
    assert "Nobody visible on camera." not in result


def test_scene_block_stale_persons_excluded():
    """Persons last seen > SCENE_STALE_SECS ago are omitted."""
    import pipeline as _pl
    from core.config import SCENE_STALE_SECS
    now = 1000.0
    persons = {"p1": {"name": "Old", "last_seen": now - SCENE_STALE_SECS - 1, "conf": 0.9}}
    result = _pl._build_scene_block(None, now, {}, persons, {}, None)
    assert "Old" not in result
    assert "Nobody visible on camera." in result


def test_scene_block_voice_only_offscreen():
    """Voice-only session not in persons_in_frame → listed under offscreen."""
    import pipeline as _pl
    from core.session_state import SessionSnapshot, VoiceEvidence
    now = 1000.0
    sessions = (SessionSnapshot(
        person_id="p2", person_name="Ajay", person_type="known",
        session_type="voice", started_at=now - 60, last_face_seen=now - 60,
        last_spoke_at=now - 5, voice_confidence=0.8, evidence=VoiceEvidence(),
        room_session_id=None, user_turns=0, kairos_clock_reset=True,
        voice_only_origin=True, waiting_for_name=False, voice_face_confirmed=False,
        db_enrolled=False, confidence_tier="", prior_person_type=None,
        dispute_reason=None, disputed_claimed_name=None, dispute_set_at=None, dispute_set_at_monotonic=None,
        disputed_block_count=0, disputed_block_alerted=False, recent_voice_confs=[],
        cached_prefix=None, core_memory=[], tool_repeat_last=None,
        tool_repeat_count=0, recent_attributions=[],
    ),)
    result = _pl._build_scene_block("p1", now, sessions, {}, {}, None)
    assert "Offscreen voice:" in result
    assert "Ajay (known) — heard 5s ago" in result


def test_scene_block_voice_stale_excluded():
    """Voice session older than SCENE_VOICE_STALE → not listed."""
    import pipeline as _pl
    from core.config import SCENE_VOICE_STALE
    from core.session_state import SessionSnapshot, VoiceEvidence
    now = 1000.0
    sessions = (SessionSnapshot(
        person_id="p2", person_name="Gone", person_type="known",
        session_type="voice", started_at=now - 200, last_face_seen=now - 200,
        last_spoke_at=now - SCENE_VOICE_STALE - 1, voice_confidence=0.7,
        evidence=VoiceEvidence(), room_session_id=None, user_turns=0,
        kairos_clock_reset=True, voice_only_origin=True, waiting_for_name=False,
        voice_face_confirmed=False, db_enrolled=False, confidence_tier="",
        prior_person_type=None, dispute_reason=None, disputed_claimed_name=None,
        dispute_set_at=None, dispute_set_at_monotonic=None, disputed_block_count=0, disputed_block_alerted=False,
        recent_voice_confs=[], cached_prefix=None, core_memory=[],
        tool_repeat_last=None, tool_repeat_count=0, recent_attributions=[],
    ),)
    result = _pl._build_scene_block(None, now, sessions, {}, {}, None)
    assert "Gone" not in result
    assert "Offscreen voice:" not in result


def test_scene_block_recent_visitors_section_fires_within_window():
    """Session 108 Phase 3A.7: when the caller supplies recent visitor
    alerts within SCENE_VISITOR_RECENCY_SECS, the SCENE block renders a
    'Recent visitors' section with human-readable lines. The brain
    uses this to proactively acknowledge "Lexi just left" without
    needing to call search_memory."""
    import pipeline as _pl
    from core.config import SCENE_VISITOR_RECENCY_SECS
    now = 1000.0
    recent = [
        {
            "generated_at": now - 120,  # 2 min ago, well inside window
            "metadata": {
                "visitor_id":    "lexi_xyz",
                "visitor_name":  "Lexi",
                "visitor_type":  "known",
                "turn_count":    11,
                "safety_flags":  [],
            },
        },
    ]
    result = _pl._build_scene_block(
        None, now, {}, {}, {}, "bf_001",
        recent_visitors=recent,
    )
    assert "Recent visitors:" in result, (
        "new section header must render when recent visitors present"
    )
    assert "Lexi" in result
    assert "promoted visitor" in result, (
        "visitor_type='known' renders as 'promoted visitor' role label"
    )
    assert "2 min ago" in result or "just now" in result


def test_scene_block_recent_visitors_excluded_outside_window():
    """Session 108 Phase 3A.7: visitors whose alert generated_at is
    older than SCENE_VISITOR_RECENCY_SECS must NOT render. TTL keeps
    the section focused on 'within-the-minute' context; older context
    is already covered by search_memory + VISITOR_CONTEXT block."""
    import pipeline as _pl
    from core.config import SCENE_VISITOR_RECENCY_SECS
    now = 1000.0
    recent = [
        {
            "generated_at": now - (SCENE_VISITOR_RECENCY_SECS + 60),
            "metadata": {
                "visitor_id":   "lexi_xyz",
                "visitor_name": "Lexi",
                "visitor_type": "known",
                "turn_count":   11,
                "safety_flags": [],
            },
        },
    ]
    result = _pl._build_scene_block(
        None, now, {}, {}, {}, "bf_001",
        recent_visitors=recent,
    )
    assert "Recent visitors:" not in result, (
        "stale visitor must not appear in Recent visitors section"
    )
    assert "Lexi" not in result


def test_scene_block_safety_concerns_section_surfaces_flags():
    """Session 108 Phase 3A.7: when a recent visitor's alert metadata
    contains safety_flags (set by Session 105 Bug N Part 3 in
    _run_visitor_alert), the SCENE block renders a dedicated 'Safety
    concerns' section as the LAST section — so the brain reads it
    after the factual context. Flags render as human-readable text
    (underscores → spaces) attributed to the visitor."""
    import pipeline as _pl
    now = 1000.0
    recent = [
        {
            "generated_at": now - 60,
            "metadata": {
                "visitor_id":    "lexi_xyz",
                "visitor_name":  "Lexi",
                "visitor_type":  "known",
                "turn_count":    13,
                "safety_flags":  [
                    "expressed_suicidal_thoughts",
                    "mentioned_self_harm",
                ],
            },
        },
    ]
    result = _pl._build_scene_block(
        None, now, {}, {}, {}, "bf_001",
        recent_visitors=recent,
    )
    assert "Safety concerns (raised during recent visits):" in result
    assert "Lexi: expressed suicidal thoughts" in result, (
        "safety flag must render human-readable (underscores stripped) "
        "and attribute the concern to the visitor"
    )
    assert "Lexi: mentioned self harm" in result
    # Safety concerns must be LAST content section before <<<END SCENE>>>.
    safety_idx = result.find("Safety concerns")
    end_idx    = result.find("<<<END SCENE>>>")
    recent_idx = result.find("Recent visitors:")
    assert 0 < recent_idx < safety_idx < end_idx, (
        "section ordering must be: Recent visitors THEN Safety concerns "
        "THEN end marker — otherwise brain reads safety first and it "
        "dominates the scene narrative"
    )


def test_scene_block_no_recent_visitors_omits_both_sections():
    """Session 108 Phase 3A.7: when no recent visitors supplied OR all
    stale, both the Recent visitors and Safety concerns sections are
    omitted entirely. Single-person no-visitor scenes keep the SCENE
    block terse (reviewer's lean-approach goal — sections render
    conditionally, not always)."""
    import pipeline as _pl
    from core.session_state import SessionSnapshot, VoiceEvidence
    now = 1000.0
    persons = {"jagan": {"name": "Jagan", "last_seen": now - 1, "conf": 0.9}}
    sessions = (SessionSnapshot(
        person_id="jagan", person_name="Jagan", person_type="best_friend",
        session_type="face", started_at=now - 60, last_face_seen=now - 1,
        last_spoke_at=now, voice_confidence=1.0, evidence=VoiceEvidence(),
        room_session_id=None, user_turns=0, kairos_clock_reset=True,
        voice_only_origin=False, waiting_for_name=False, voice_face_confirmed=False,
        db_enrolled=False, confidence_tier="", prior_person_type=None,
        dispute_reason=None, disputed_claimed_name=None, dispute_set_at=None, dispute_set_at_monotonic=None,
        disputed_block_count=0, disputed_block_alerted=False, recent_voice_confs=[],
        cached_prefix=None, core_memory=[], tool_repeat_last=None,
        tool_repeat_count=0, recent_attributions=[],
    ),)
    # No recent_visitors passed at all.
    result = _pl._build_scene_block(
        "jagan", now, sessions, persons, {}, "jagan",
    )
    assert "Recent visitors:" not in result
    assert "Safety concerns" not in result
    # And with empty list explicitly.
    result2 = _pl._build_scene_block(
        "jagan", now, sessions, persons, {}, "jagan",
        recent_visitors=[],
    )
    assert "Recent visitors:" not in result2
    assert "Safety concerns" not in result2


def test_scene_block_stranger_role_label():
    """Stranger session → role='visitor'."""
    import pipeline as _pl
    from core.session_state import SessionSnapshot, VoiceEvidence
    now = 1000.0
    persons = {"s1": {"name": "visitor", "last_seen": now - 1, "conf": 0.5}}
    sessions = (SessionSnapshot(
        person_id="s1", person_name="visitor", person_type="stranger",
        session_type="face", started_at=now - 60, last_face_seen=now - 1,
        last_spoke_at=now, voice_confidence=0.5, evidence=VoiceEvidence(),
        room_session_id="room_test", user_turns=0, kairos_clock_reset=True,
        voice_only_origin=False, waiting_for_name=False, voice_face_confirmed=False,
        db_enrolled=False, confidence_tier="", prior_person_type=None,
        dispute_reason=None, disputed_claimed_name=None, dispute_set_at=None, dispute_set_at_monotonic=None,
        disputed_block_count=0, disputed_block_alerted=False, recent_voice_confs=[],
        cached_prefix=None, core_memory=[], tool_repeat_last=None,
        tool_repeat_count=0, recent_attributions=[],
    ),)
    result = _pl._build_scene_block(None, now, sessions, persons, {}, "bf1")
    assert "visitor (visitor)" in result


def test_scene_block_disputed_best_friend_labeled_disputed():
    """Finding M — disputed session must NOT render as 'best friend' even when
    the pid matches best_friend_id. The SCENE block must agree with the
    IDENTITY DISPUTED block rather than contradict it."""
    import pipeline as _pl
    from core.session_state import SessionSnapshot, VoiceEvidence
    now = 1000.0
    persons = {"jagan_bf": {"name": "Jagan", "last_seen": now - 1, "conf": 0.55}}
    sessions = (SessionSnapshot(
        person_id="jagan_bf", person_name="Jagan", person_type="disputed",
        session_type="face", started_at=now - 60, last_face_seen=now - 1,
        last_spoke_at=now, voice_confidence=0.55, evidence=VoiceEvidence(),
        room_session_id="room_test", user_turns=0, kairos_clock_reset=True,
        voice_only_origin=False, waiting_for_name=False, voice_face_confirmed=False,
        db_enrolled=False, confidence_tier="", prior_person_type=None,
        dispute_reason=None, disputed_claimed_name=None, dispute_set_at=None, dispute_set_at_monotonic=None,
        disputed_block_count=0, disputed_block_alerted=False, recent_voice_confs=[],
        cached_prefix=None, core_memory=[], tool_repeat_last=None,
        tool_repeat_count=0, recent_attributions=[],
    ),)
    # Seed the store so _is_disputed("jagan_bf") returns True.
    import asyncio
    asyncio.run(_pl._session_store.open_session(
        "jagan_bf", "Jagan", "known", "face", now=now
    ))
    asyncio.run(_pl._session_store.transition_to_disputed(
        "jagan_bf", None, "test dispute", now=now
    ))
    # Note the best_friend_id matches the disputed pid — the dispute must win.
    result = _pl._build_scene_block("jagan_bf", now, sessions, persons, {}, "jagan_bf")
    assert "Jagan (disputed identity) — speaking now" in result
    # Must NOT label this person as best friend in the SCENE block
    assert "(best friend)" not in result


def _make_voice_state(matched_id=None, matched_name=None, conf=0.0, matches=False, gallery_size=1):
    return {
        "matched_id": matched_id,
        "matched_name": matched_name,
        "voice_confidence": conf,
        "matches_active": matches,
        "gallery_size": gallery_size,
    }


def test_mic_status_no_gallery():
    from core.brain import _build_system_prompt
    vs = _make_voice_state(gallery_size=0)
    result = _build_system_prompt("Alice", voice_state=vs)
    assert "no voice profiles enrolled yet" in result


def test_mic_status_verified():
    from core.brain import _build_system_prompt
    vs = _make_voice_state("pid", "Alice", conf=0.72, matches=True, gallery_size=2)
    result = _build_system_prompt("Alice", voice_state=vs)
    assert "verified=YES" in result
    assert "Alice" in result


def test_mic_status_different_speaker():
    from core.brain import _build_system_prompt
    vs = _make_voice_state("other_pid", "Bob", conf=0.65, matches=False, gallery_size=2)
    result = _build_system_prompt("Alice", voice_state=vs)
    assert "verified=NO" in result
    assert "another person is likely speaking" in result


def test_mic_status_below_threshold():
    from core.brain import _build_system_prompt
    vs = _make_voice_state(matched_id=None, conf=0.18, gallery_size=3)
    result = _build_system_prompt("Alice", voice_state=vs)
    assert "below match threshold" in result
    assert "3 profile" in result


def test_mic_status_too_short():
    from core.brain import _build_system_prompt
    vs = _make_voice_state(matched_id=None, conf=0.0, gallery_size=2)
    result = _build_system_prompt("Alice", voice_state=vs)
    assert "too short for voice ID" in result


def _make_multi_voice_state(s0: str, s1: str):
    return {
        "matched_id": None,
        "matched_name": None,
        "voice_confidence": 0.0,
        "matches_active": False,
        "gallery_size": 2,
        "multi_speaker": True,
        "multi_speaker_speakers": [s0, s1],
    }


def test_mic_status_multi_speaker_shows_both_names():
    from core.brain import _build_system_prompt
    vs = _make_multi_voice_state("Alice", "Bob")
    result = _build_system_prompt("Alice", voice_state=vs)
    assert "2 speakers detected" in result
    assert "Alice" in result
    assert "Bob" in result


def test_mic_status_multi_speaker_includes_annotation_hint():
    from core.brain import _build_system_prompt
    vs = _make_multi_voice_state("Jagan", "Sweetie")
    result = _build_system_prompt("Jagan", voice_state=vs)
    assert "[Name]" in result or "annotated" in result


def test_mic_status_multi_speaker_false_falls_through_to_normal():
    from core.brain import _build_system_prompt
    vs = {
        "matched_id": "pid1",
        "matched_name": "Alice",
        "voice_confidence": 0.75,
        "matches_active": True,
        "gallery_size": 2,
        "multi_speaker": False,
        "multi_speaker_speakers": [],
    }
    result = _build_system_prompt("Alice", voice_state=vs)
    assert "verified=YES" in result
    assert "2 speakers" not in result


def test_voice_state_dicts_include_multi_speaker_keys():
    import inspect, pipeline
    src = inspect.getsource(pipeline)
    assert '"multi_speaker":' in src, "both _voice_state dicts must have multi_speaker key"
    assert '"multi_speaker_speakers":' in src, "both _voice_state dicts must have multi_speaker_speakers key"


def test_no_direct_is_live_calls_in_pipeline():
    import inspect, pipeline
    src = inspect.getsource(pipeline)
    assert "_anti_spoof_checker.is_live(" not in src, \
        "pipeline.py must not call is_live() directly — use verify_live()"


def test_no_direct_is_live_calls_in_enroll():
    import importlib, inspect
    import enroll
    src = inspect.getsource(enroll)
    assert "anti_spoof.is_live(" not in src, \
        "enroll.py must not call is_live() directly — use verify_live()"


def test_persons_in_frame_pruning_uses_inplace_pop_not_dict_rewrite():
    """Wave 1 Item 8: the stale-entry pruning path must use in-place
    mutation on the PresenceStore instead of rebinding a dict to a new
    comprehension.

    Dict-rebind (_persons_in_frame = {comprehension}) creates a new dict
    object, breaking any other coroutine that holds a reference to the
    original dict. Since P0.6.2 the canonical pruning API is
    _presence_store.prune_stale(cutoff_ts), which mutates store state
    in-place without a module-global rebind."""
    import inspect, pipeline
    src = inspect.getsource(pipeline._background_vision_loop)

    # The dict-rewrite pattern must be gone.
    assert "_persons_in_frame = {" not in src, (
        "Wave 1 Item 8: _persons_in_frame must not be rebound to a new dict "
        "comprehension in _background_vision_loop(). Use _presence_store.prune_stale() instead."
    )

    # The PresenceStore prune_stale call must be present.
    assert "_presence_store.prune_stale(" in src, (
        "Wave 1 Item 8: _presence_store.prune_stale() must be used to prune stale "
        "entries in-place via the PresenceStore API."
    )
