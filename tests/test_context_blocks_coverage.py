"""100% line coverage for runtime.context_blocks — coverage-to-100 campaign.

Targets the previously-uncovered lines:
  - 30-33   `_infer_zone` body (bbox → normalized center → brain zone helper)
  - 114-115 `_set_state` `except RuntimeError: pass` (no running loop, sync ctx)
  - 140-154 `_scene_fingerprint` per-pid loop: stale-skip + every role branch
            (disputed / best_friend / visitor / known, incl. both sides of the
            `_snap is not None` ternary)
  - 182     `_get_scene_block_cached` cache-disabled early return
  - 205     `get_scene_block_cache_stats` peek_stats passthrough
  - 285     `_build_scene_block` offscreen-voice best-friend role
  - 287     `_build_scene_block` offscreen-voice visitor role
  - 306     `_build_scene_block` recent_visitors non-dict skip
  - 318     `_build_scene_block` recent_visitors owner-is-own-visitor skip

Portability: `runtime.context_blocks` transitively imports `core.brain_agent`,
which hard-imports `kuzu` at module scope. `kuzu` is an optional native dep that
may be absent in the minimal fast-CI env, so the whole module is guarded with
`pytest.importorskip("kuzu")` — it runs (and provides coverage) in the full env
and skips cleanly headless where kuzu is absent. `core.voice`/`core.audio` are
already stubbed by the module-scope `setup_pipeline_stubs()` in tests/conftest.py
(imported before this file is collected), so the import chain is headless — no
GPU/camera/network/model downloads. Session state is seeded on the REAL
SessionStore; only `core.state.write` (a filesystem/IPC boundary) is mocked.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

import pytest

pytest.importorskip("kuzu")  # optional native dep pulled in via core.brain_agent

import runtime.wiring as _wiring
import runtime.context_blocks as cb
from core.session_state import Session, SessionSnapshot, VoiceEvidence
from runtime.state_enums import PipelineState


# ─────────────────────────────────────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────────────────────────────────────

def _snap(
    person_id,
    *,
    person_name=None,
    person_type="known",
    session_type="face",
    last_spoke_at=0.0,
) -> SessionSnapshot:
    """Build a real (frozen) SessionSnapshot — only the fields the production
    code reads matter, but all 30 are filled so the real dataclass is exercised.
    """
    return SessionSnapshot(
        person_id=person_id,
        person_name=person_name if person_name is not None else person_id,
        person_type=person_type,
        session_type=session_type,
        started_at=0.0,
        last_face_seen=0.0,
        last_spoke_at=last_spoke_at,
        voice_confidence=1.0,
        evidence=VoiceEvidence(),
        room_session_id="",
        user_turns=0,
        kairos_clock_reset=True,
        voice_only_origin=False,
        waiting_for_name=False,
        voice_face_confirmed=False,
        db_enrolled=False,
        confidence_tier="",
        prior_person_type=None,
        dispute_reason=None,
        disputed_claimed_name=None,
        dispute_set_at=None,
        dispute_set_at_monotonic=None,
        disputed_block_count=0,
        disputed_block_alerted=False,
        recent_voice_confs=(),
        cached_prefix=None,
        core_memory=(),
        tool_repeat_last=None,
        tool_repeat_count=0,
        recent_attributions=(),
    )


def _seed_disputed_session(pid: str, now: float) -> None:
    """Insert a real disputed Session into the (fresh, per-test) SessionStore so
    `_is_disputed(pid)` returns True via the genuine peek_snapshot path."""
    _wiring._session_store._sessions[pid] = Session(
        person_id=pid,
        person_name=pid,
        person_type="disputed",
        session_type="face",
        started_at=now,
        last_face_seen=now,
        last_spoke_at=now,
    )


# ─────────────────────────────────────────────────────────────────────────────
# _infer_zone  (lines 30-33)
# ─────────────────────────────────────────────────────────────────────────────

def test_infer_zone_maps_bbox_to_zone():
    # bbox center (50, 50) over a 200x200 frame -> cx=cy=0.25 -> left/upper.
    assert cb._infer_zone((0, 0, 100, 100), 200, 200) == "left side (upper area)"


def test_infer_zone_zero_frame_dims_use_max_guard():
    # frame_w/h = 0 exercises the `max(frame_*, 1)` divide-by-zero guard:
    # cx=cy = 50/1 = 50.0 -> right side / floor level.
    assert cb._infer_zone((0, 0, 100, 100), 0, 0) == "right side (floor level)"


# ─────────────────────────────────────────────────────────────────────────────
# _set_state  (lines 114-115: except RuntimeError branch — no running loop)
# ─────────────────────────────────────────────────────────────────────────────

def test_set_state_no_running_loop_swallows_runtime_error(monkeypatch):
    # SYNC test => asyncio.get_running_loop() raises RuntimeError => lines 114-115
    # `except RuntimeError: pass`. The final state.write is a filesystem/IPC
    # boundary — mock it so the test stays headless and side-effect free.
    calls = []
    monkeypatch.setattr(cb.state, "write", lambda **kw: calls.append(kw))

    # Current state is WATCHING (fresh store from the autouse fixture); assert
    # explicitly so a differing new_state guarantees we pass the equality guard.
    _wiring._pipeline_state_store._pipeline_state = PipelineState.WATCHING

    # No exception should escape even though there is no running event loop.
    cb._set_state(PipelineState.THINKING, person_name="Bob")

    assert calls == [{"mode": "thinking", "current_person": "Bob"}]


def test_set_state_noop_when_already_current(monkeypatch):
    # Equality guard (line 108-109) returns before touching state.write.
    calls = []
    monkeypatch.setattr(cb.state, "write", lambda **kw: calls.append(kw))
    _wiring._pipeline_state_store._pipeline_state = PipelineState.WATCHING

    cb._set_state(PipelineState.WATCHING)

    assert calls == []


# ─────────────────────────────────────────────────────────────────────────────
# _scene_fingerprint  (lines 140-154: stale-skip + all role branches)
# ─────────────────────────────────────────────────────────────────────────────

def test_scene_fingerprint_covers_stale_skip_and_all_roles():
    now = 1000.0
    _seed_disputed_session("disp", now)

    persons_in_frame = {
        # elapsed >> SCENE_STALE_SECS (5.0) -> line 141 `continue`
        "stale": {"last_seen": now - 1_000_000.0, "name": "Stale"},
        # recent + disputed session -> role "disputed" (lines 145-146)
        "disp": {"last_seen": now, "name": "Disp"},
        # recent + pid == best_friend_id -> role "best_friend" (lines 147-148)
        "bf": {"last_seen": now, "name": "BF"},
        # recent + snapshot person_type "stranger" -> role "visitor" (149-150)
        "vis": {"last_seen": now, "name": "Vis"},
        # recent + NO snapshot -> `_snap is None` -> "known" else branch (151-152)
        "known": {"last_seen": now, "name": "Known"},
    }
    active_sessions = (
        _snap("disp", person_type="disputed"),   # _snap is not None side
        _snap("bf", person_type="known"),
        _snap("vis", person_type="stranger"),
        # "known" intentionally absent -> exercises the `else "known"` ternary side
    )
    unrecognized_tracks = {"u1": {"last_seen": now}}
    recent_visitors = [
        {"person_id": "v1", "visitor_name": "V1", "safety_flags": []},
    ]

    fp = cb._scene_fingerprint(
        "disp",  # speaker_id == "disp" -> exercises `pid == speaker_id` True side
        now,
        active_sessions,
        persons_in_frame,
        unrecognized_tracks,
        "bf",
        recent_visitors,
    )

    # fp = (speaker_id, now_sec, frozenset(vis_items), unrec_count, bf_id, rv_key)
    assert fp[0] == "disp"
    assert fp[4] == "bf"
    vis_items = fp[2]
    roles = {item[0]: item[2] for item in vis_items}
    speaking = {item[0]: item[3] for item in vis_items}

    assert "stale" not in roles          # stale entry skipped (line 141)
    assert roles["disp"] == "disputed"   # 145-146
    assert roles["bf"] == "best_friend"  # 147-148
    assert roles["vis"] == "visitor"     # 149-150
    assert roles["known"] == "known"     # 151-152 (_snap is None side)
    assert speaking["disp"] is True      # pid == speaker_id True side (line 154)
    assert speaking["known"] is False    # pid != speaker_id False side


# ─────────────────────────────────────────────────────────────────────────────
# _get_scene_block_cached  (line 182: cache-disabled early return)
# ─────────────────────────────────────────────────────────────────────────────

async def test_get_scene_block_cached_disabled_returns_direct_build(monkeypatch):
    monkeypatch.setattr(cb, "SCENE_BLOCK_CACHE_ENABLED", False)
    now = 1000.0

    result = await cb._get_scene_block_cached(
        None, now, (), {}, {}, None, None,
    )
    direct = cb._build_scene_block(None, now, (), {}, {}, None, None)

    assert result == direct
    assert "<<<SCENE" in result


async def test_get_scene_block_cached_enabled_miss_then_hit(monkeypatch):
    # Cache-enabled round-trip: first call misses (compute + set), second hits.
    monkeypatch.setattr(cb, "SCENE_BLOCK_CACHE_ENABLED", True)
    now = 1000.0
    args = (None, now, (), {}, {}, None, None)

    first = await cb._get_scene_block_cached(*args)
    second = await cb._get_scene_block_cached(*args)

    assert first == second
    stats = cb.get_scene_block_cache_stats()
    assert stats["hits"] >= 1
    assert stats["misses"] >= 1


# ─────────────────────────────────────────────────────────────────────────────
# get_scene_block_cache_stats  (line 205)
# ─────────────────────────────────────────────────────────────────────────────

def test_get_scene_block_cache_stats_shape():
    stats = cb.get_scene_block_cache_stats()
    assert isinstance(stats, dict)
    assert stats["name"] == "scene_block"
    for key in ("hits", "misses", "size", "max_entries"):
        assert key in stats


# ─────────────────────────────────────────────────────────────────────────────
# _build_scene_block offscreen voice  (lines 285 best_friend / 287 visitor)
# ─────────────────────────────────────────────────────────────────────────────

def test_build_scene_block_offscreen_roles():
    now = 1000.0
    active_sessions = (
        # pid == best_friend_id -> role "best friend" (line 285)
        _snap("bf_off", session_type="voice", last_spoke_at=now, person_type="known"),
        # person_type "stranger" -> role "visitor" (line 287)
        _snap("vis_off", session_type="voice", last_spoke_at=now, person_type="stranger"),
    )

    out = cb._build_scene_block(
        "someone_else",   # != any offscreen pid -> "heard Ns ago" status branch
        now,
        active_sessions,
        {},               # empty persons_in_frame -> nobody on camera
        {},               # no unrecognized tracks
        "bf_off",         # best_friend_id
        None,             # no recent visitors
    )

    assert "Offscreen voice:" in out
    assert "bf_off (best friend)" in out   # line 285
    assert "vis_off (visitor)" in out      # line 287
    assert "Nobody visible on camera." in out


def test_build_scene_block_offscreen_skips_non_voice_and_stale_and_visible():
    now = 1000.0
    active_sessions = (
        # in persons_in_frame -> skipped by the `pid in persons_in_frame` guard
        _snap("onscreen", session_type="voice", last_spoke_at=now),
        # session_type != "voice" -> skipped
        _snap("face_only", session_type="face", last_spoke_at=now),
        # stale offscreen voice (last_spoke far past SCENE_VOICE_STALE=30) -> skipped
        _snap("stale_voice", session_type="voice", last_spoke_at=now - 10_000.0),
    )
    persons_in_frame = {"onscreen": {"last_seen": now, "name": "Onscreen"}}

    out = cb._build_scene_block(
        None, now, active_sessions, persons_in_frame, {}, None, None,
    )

    # None of the three offscreen candidates survive -> no Offscreen section.
    assert "Offscreen voice:" not in out


# ─────────────────────────────────────────────────────────────────────────────
# _build_scene_block recent_visitors  (line 306 non-dict / line 318 owner skip)
# ─────────────────────────────────────────────────────────────────────────────

def test_build_scene_block_recent_visitors_skips_non_dict_and_owner():
    now = 1000.0
    recent_visitors = [
        "not-a-dict",  # line 306: `not isinstance(v, dict)` -> continue
        {  # line 318: metadata.visitor_id == best_friend_id -> continue (owner)
            "generated_at": now,
            "metadata": {"visitor_id": "owner", "visitor_name": "Owner"},
        },
        {  # a real visitor that renders (with a safety flag rollup)
            "generated_at": now,
            "metadata": {
                "visitor_name": "Lexi",
                "visitor_id": "lexi",
                "turn_count": 3,
                "visitor_type": "known",
                "safety_flags": ["expressed_suicidal_thoughts"],
            },
        },
    ]

    out = cb._build_scene_block(
        None, now, (), {}, {}, "owner", recent_visitors,
    )

    assert "Recent visitors:" in out
    assert "Lexi (promoted visitor)" in out            # normal visitor rendered
    assert "Owner" not in out                          # owner skipped (line 318)
    assert "Safety concerns (raised during recent visits):" in out
    assert "Lexi: expressed suicidal thoughts" in out  # safety flag humanized


def test_build_scene_block_recent_visitors_stale_generated_at_skipped():
    now = 1000.0
    recent_visitors = [
        {  # generated_at far past SCENE_VISITOR_RECENCY_SECS (600) -> line 308 skip
            "generated_at": now - 100_000.0,
            "metadata": {"visitor_name": "OldGuest", "visitor_id": "old"},
        },
    ]

    out = cb._build_scene_block(
        None, now, (), {}, {}, "owner", recent_visitors,
    )

    assert "Recent visitors:" not in out
    assert "OldGuest" not in out
