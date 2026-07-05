"""Coverage-to-100 for runtime/session.py — the relocated session-lifecycle engine.

Drives the defensive/edge lines the behavioral suite never reaches: the voice-
source guard in _has_recent_face_evidence; the sync-fallback swallow paths in
_open_session; the no-session refusal in _voice_accum_allowed; the uninitialized-
RoomOrchestrator raise in _on_room_end; the stranger-prune try/except in
_close_session; the dispute re-anchor / auto-clear / vanished-session / full-
cleanup branches of _expire_stale_sessions; and the identify-match / short-
utterance / embed-success / VOICE_BOOTSTRAP_DEBUG branches of _accumulate_voice.
Hardware-free and headless: SessionStore + PipelineStateStore + the P0.6 stores
only, with core.voice.identify/embed injected as fakes (no CUDA, camera, or
model download)."""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import asyncio
import time
import types
from unittest.mock import AsyncMock, MagicMock

import pytest

import core.config as _config
import runtime.session as rt
import runtime.wiring as _wiring


# ─────────────────────────────────────────────────────────────────────────────
# _face_in_frame — helper (both branches)
# ─────────────────────────────────────────────────────────────────────────────

def test_face_in_frame_true_for_face_source():
    assert rt._face_in_frame("p", {"p": {"source": "face"}}) is True


def test_face_in_frame_false_for_voice_source():
    assert rt._face_in_frame("p", {"p": {"source": "voice"}}) is False


def test_face_in_frame_false_when_absent():
    assert rt._face_in_frame("p", {}) is False


# ─────────────────────────────────────────────────────────────────────────────
# _has_recent_face_evidence — line 54 (no source), 56 (voice source), 57-58
# ─────────────────────────────────────────────────────────────────────────────

def test_has_recent_face_evidence_no_source_returns_false():
    # No presence entry → peek_source returns "" → line 54.
    assert rt._has_recent_face_evidence("nobody-here") is False


async def test_has_recent_face_evidence_voice_source_returns_false():
    # Voice-sourced presence must NOT count as face evidence — lines 55-56.
    await _wiring._presence_store.upsert_voice_recognition(
        "v1", "Vee", 0.5, time.monotonic()
    )
    assert rt._has_recent_face_evidence("v1") is False


async def test_has_recent_face_evidence_recent_face_true():
    # Recent face-sourced presence → lines 57-58 within SCENE_STALE_SECS.
    await _wiring._presence_store.upsert_face_recognition(
        "f1", "Eff", 0.9, time.monotonic()
    )
    assert rt._has_recent_face_evidence("f1") is True


async def test_has_recent_face_evidence_stale_face_false():
    # Old face-sourced presence → line 58 evaluates False (past SCENE_STALE_SECS).
    await _wiring._presence_store.upsert_face_recognition(
        "f2", "Eff2", 0.9, time.monotonic() - 100.0
    )
    assert rt._has_recent_face_evidence("f2") is False


# ─────────────────────────────────────────────────────────────────────────────
# _is_disputed — dict path (78), empty (80-81), pid path (82-83)
# ─────────────────────────────────────────────────────────────────────────────

def test_is_disputed_dict_path():
    assert rt._is_disputed({"person_type": "disputed"}) is True
    assert rt._is_disputed({"person_type": "known"}) is False


def test_is_disputed_empty_pid_is_not_disputed():
    assert rt._is_disputed("") is False
    assert rt._is_disputed(None) is False


async def test_is_disputed_pid_path():
    _wiring._session_store._sync_open_session(
        "id1", "Ida", "known", "voice", now=time.time(), now_mono=time.monotonic()
    )
    assert rt._is_disputed("id1") is False  # not yet disputed
    await _wiring._session_store.transition_to_disputed(
        "id1", None, "test", now=time.time()
    )
    assert rt._is_disputed("id1") is True   # lines 82-83
    assert rt._is_disputed("ghost-pid") is False  # peek_snapshot → None


# ─────────────────────────────────────────────────────────────────────────────
# _open_session — line 138-139: pop_emotion_agent sync-fallback swallows
# ─────────────────────────────────────────────────────────────────────────────

def test_open_session_pop_emotion_agent_sync_fallback_swallows(monkeypatch):
    """No running loop → asyncio.run(pop_emotion_agent). If that raises, the
    inner `except Exception: pass` (lines 138-139) swallows it; the open
    completes."""
    monkeypatch.setattr(_wiring, "_face_db_ref", None)
    monkeypatch.setattr(_wiring, "_brain_orchestrator", None)

    async def _boom_pop(pid):
        raise ValueError("pop boom")

    monkeypatch.setattr(_wiring._per_person_agent_store, "pop_emotion_agent", _boom_pop)

    # Sync context → line 131 raises RuntimeError → the sync fallback at 137 runs
    # asyncio.run(...) which raises → 138-139 swallow.
    rt._open_session("boomer", "Boomer", "voice", "stranger")

    snap = _wiring._session_store.peek_snapshot("boomer")
    assert snap is not None
    assert snap.person_type == "stranger"


# ─────────────────────────────────────────────────────────────────────────────
# _open_session — lines 200-201 (set_gallery create_task, no loop) + 202-203
# ─────────────────────────────────────────────────────────────────────────────

def test_open_session_gallery_repair_no_loop_swallows(monkeypatch):
    """Cache/DB voice-count mismatch + no running loop → the set_gallery
    create_task raises RuntimeError → inner `except RuntimeError: pass`
    (lines 200-201)."""
    monkeypatch.setattr(_wiring, "_brain_orchestrator", None)

    face_db = MagicMock()
    face_db.count_voice_embeddings.return_value = 5   # DB says 5
    monkeypatch.setattr(_wiring, "_face_db_ref", face_db)

    # Seed the cache with a DIFFERENT size (3) + a non-None embedding so the
    # repair branch (194-199) runs.
    asyncio.run(_wiring._voice_gallery_store.set_gallery("gr1", [1.0, 2.0, 3.0], 3))

    rt._open_session("gr1", "Gee", "voice", "stranger")  # sync → 198 raises → 200-201

    face_db.count_voice_embeddings.assert_called_once_with("gr1")
    assert _wiring._session_store.peek_snapshot("gr1") is not None


def test_open_session_gallery_repair_count_error_swallows(monkeypatch):
    """count_voice_embeddings raising → the OUTER `except Exception: pass`
    (lines 202-203) swallows it; the open completes with the cached fallback."""
    monkeypatch.setattr(_wiring, "_brain_orchestrator", None)

    face_db = MagicMock()
    face_db.count_voice_embeddings.side_effect = ValueError("db down")
    monkeypatch.setattr(_wiring, "_face_db_ref", face_db)

    rt._open_session("gr2", "Gee2", "voice", "stranger")

    face_db.count_voice_embeddings.assert_called_once_with("gr2")
    assert _wiring._session_store.peek_snapshot("gr2") is not None


# ─────────────────────────────────────────────────────────────────────────────
# _voice_accum_allowed — line 323: no session
# ─────────────────────────────────────────────────────────────────────────────

def test_voice_accum_allowed_refuses_when_no_session():
    allowed, reason, path = rt._voice_accum_allowed("no-such-session")
    assert allowed is False
    assert reason == "no session"
    assert path == "refused"


# ─────────────────────────────────────────────────────────────────────────────
# _on_room_end — line 361 (raise) + line 365 (delegate)
# ─────────────────────────────────────────────────────────────────────────────

async def test_on_room_end_raises_when_orchestrator_uninitialized(monkeypatch):
    monkeypatch.setattr(_wiring, "_room_orchestrator", None)
    with pytest.raises(RuntimeError, match="RoomOrchestrator not initialized"):
        await rt._on_room_end("room_x")


async def test_on_room_end_delegates_to_orchestrator(monkeypatch):
    ro = MagicMock()
    ro.on_room_end = AsyncMock()
    monkeypatch.setattr(_wiring, "_room_orchestrator", ro)

    await rt._on_room_end("room_y", ["p1", "p2"], 123.0)

    ro.on_room_end.assert_awaited_once_with("room_y", ["p1", "p2"], 123.0)


# ─────────────────────────────────────────────────────────────────────────────
# _close_session — lines 380-381 (prune ok) + 382-383 (prune raises)
# ─────────────────────────────────────────────────────────────────────────────

def test_close_session_stranger_prunes_zero_value(monkeypatch):
    monkeypatch.setattr(_wiring, "_brain_orchestrator", None)
    face_db = MagicMock()
    monkeypatch.setattr(_wiring, "_face_db_ref", face_db)

    _wiring._session_store._sync_open_session(
        "s1", "Stan", "stranger", "voice", now=time.time(), now_mono=time.monotonic()
    )
    rt._close_session("s1")

    face_db.prune_zero_value_stranger.assert_called_once_with("s1")
    assert _wiring._session_store.peek_snapshot("s1") is None


def test_close_session_stranger_prune_error_swallows(monkeypatch):
    monkeypatch.setattr(_wiring, "_brain_orchestrator", None)
    face_db = MagicMock()
    face_db.prune_zero_value_stranger.side_effect = RuntimeError("prune boom")
    monkeypatch.setattr(_wiring, "_face_db_ref", face_db)

    _wiring._session_store._sync_open_session(
        "s2", "Stan2", "stranger", "voice", now=time.time(), now_mono=time.monotonic()
    )
    rt._close_session("s2")  # must not raise — lines 382-383 swallow + log.

    face_db.prune_zero_value_stranger.assert_called_once_with("s2")
    assert _wiring._session_store.peek_snapshot("s2") is None


def test_close_session_non_stranger_skips_prune(monkeypatch):
    """A known session must NOT hit prune (line 379 False side)."""
    monkeypatch.setattr(_wiring, "_brain_orchestrator", None)
    face_db = MagicMock()
    monkeypatch.setattr(_wiring, "_face_db_ref", face_db)

    _wiring._session_store._sync_open_session(
        "k1", "Kay", "known", "voice", now=time.time(), now_mono=time.monotonic()
    )
    rt._close_session("k1")

    face_db.prune_zero_value_stranger.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# _expire_stale_sessions — line 521: dispute re-anchor create_task (running loop)
# ─────────────────────────────────────────────────────────────────────────────

async def test_expire_reanchors_dispute_monotonic_in_running_loop():
    """A disputed session with dispute_set_at_monotonic=None + a running loop
    reaches the create_task re-anchor at line 521 (not the sync fallback)."""
    _wiring._session_store._sync_open_session(
        "d1", "Dee", "known", "voice", now=time.time(), now_mono=time.monotonic()
    )
    # now_mono omitted → dispute_set_at_monotonic stays None → triggers re-anchor.
    await _wiring._session_store.transition_to_disputed(
        "d1", None, "test", now=time.time()
    )
    assert _wiring._session_store.peek_snapshot("d1").dispute_set_at_monotonic is None

    result = rt._expire_stale_sessions()  # sync call, but a loop IS running here
    assert result is False  # session is fresh → not expired

    await asyncio.sleep(0.05)  # let the scheduled set_dispute_set_at task drain
    snap = _wiring._session_store.peek_snapshot("d1")
    assert snap is not None
    assert snap.dispute_set_at_monotonic is not None  # re-anchor task stamped it


# ─────────────────────────────────────────────────────────────────────────────
# _expire_stale_sessions — lines 579 (clear_dispute task) + 583 (notify brain)
# ─────────────────────────────────────────────────────────────────────────────

async def test_expire_auto_clears_dispute_and_notifies_orchestrator(monkeypatch):
    """3 consecutive strong voice confs auto-clear a dispute: the running-loop
    create_task at 579 fires + the brain orchestrator is notified at 583."""
    from core.config import (
        DISPUTE_AUTO_CLEAR_CONSECUTIVE_TURNS,
        DISPUTE_AUTO_CLEAR_VOICE_SOLO_MIN,
    )

    brain = MagicMock()
    monkeypatch.setattr(_wiring, "_brain_orchestrator", brain)

    _wiring._session_store._sync_open_session(
        "d2", "Dee2", "known", "voice", now=time.time(), now_mono=time.monotonic()
    )
    # now_mono set → dispute_set_at_monotonic NOT None → skips the re-anchor.
    await _wiring._session_store.transition_to_disputed(
        "d2", None, "test", now=time.time(), now_mono=time.monotonic()
    )
    strong = DISPUTE_AUTO_CLEAR_VOICE_SOLO_MIN + 0.05
    for _ in range(DISPUTE_AUTO_CLEAR_CONSECUTIVE_TURNS):
        await _wiring._session_store.append_voice_conf("d2", conf=strong)

    result = rt._expire_stale_sessions()  # running loop → 579 create_task path
    assert result is False

    brain.clear_disputed.assert_called_once_with("d2")  # line 583, synchronous

    await asyncio.sleep(0.05)  # drain the clear_dispute task (579)
    snap = _wiring._session_store.peek_snapshot("d2")
    assert snap is not None
    assert snap.person_type == "known"  # prior_person_type restored


async def test_expire_auto_clears_dispute_via_face_corroboration(monkeypatch):
    """Face-in-frame + strong face_match_conf clears a dispute with no voice
    confs — exercises the _face_confirmed side of line 560 + notifies at 583."""
    from core.config import DISPUTE_AUTO_CLEAR_VOICE_MIN

    brain = MagicMock()
    monkeypatch.setattr(_wiring, "_brain_orchestrator", brain)

    _wiring._session_store._sync_open_session(
        "d3", "Dee3", "known", "voice", now=time.time(), now_mono=time.monotonic()
    )
    await _wiring._session_store.transition_to_disputed(
        "d3", None, "test", now=time.time(), now_mono=time.monotonic()
    )
    await _wiring._session_store.update_face_seen(
        "d3", conf=DISPUTE_AUTO_CLEAR_VOICE_MIN + 0.1, ts=time.monotonic()
    )
    await _wiring._presence_store.upsert_face_recognition(
        "d3", "Dee3", 0.9, time.monotonic()
    )

    result = rt._expire_stale_sessions()
    assert result is False
    brain.clear_disputed.assert_called_once_with("d3")


# ─────────────────────────────────────────────────────────────────────────────
# _expire_stale_sessions — line 607: expired pid whose snapshot vanished
# ─────────────────────────────────────────────────────────────────────────────

def test_expire_skips_vanished_expired_session(monkeypatch):
    """A pid collected into `_expired` from peek_all_snapshots but gone by the
    second-pass peek_snapshot → `if _snap_exp is None: continue` (606-607)."""
    ghost = types.SimpleNamespace(
        person_id="ghost",
        session_type="face",
        last_face_seen=-1.0e9,   # guaranteed stale vs monotonic now
    )

    class _RaceStore:
        def peek_all_snapshots(self):
            return [ghost]

        def peek_snapshot(self, pid):
            return None

    monkeypatch.setattr(_wiring, "_session_store", _RaceStore())

    result = rt._expire_stale_sessions()
    assert result is True  # ghost collected, but its close was skipped via continue


# ─────────────────────────────────────────────────────────────────────────────
# _expire_stale_sessions — real expiry: sync fallbacks + notify + full cleanup
# (lines 614-616, 618, 629-630, 633-634 + the 622-634 all-closed cleanup block)
# ─────────────────────────────────────────────────────────────────────────────

def test_expire_real_session_sync_fallbacks_and_full_cleanup(monkeypatch):
    """A stale face session expiring in a NO-loop (sync) context: the pop_history/
    touch_greeted sync fallbacks (614-616), the brain notify (618), and the
    all-sessions-closed cleanup with its own sync fallbacks (629-630, 633-634)."""
    brain = MagicMock()
    monkeypatch.setattr(_wiring, "_brain_orchestrator", brain)
    monkeypatch.setattr(_wiring, "_face_db_ref", None)

    _wiring._session_store._sync_open_session(
        "exp1", "Ex", "known", "face", now=time.time(), now_mono=time.monotonic()
    )
    # Backdate last_face_seen far past FACE_LOSS_GRACE so the next sweep expires it.
    _wiring._session_store._sessions["exp1"].last_face_seen = time.monotonic() - 10_000.0

    result = rt._expire_stale_sessions()  # sync context — no running loop

    assert result is True
    brain.notify_session_end.assert_called_once_with("exp1")   # line 618
    assert _wiring._session_store.peek_snapshot("exp1") is None  # closed
    # Full-cleanup ran (no sessions remain); detected_lang reset to "en" (633-634).
    assert _wiring._pipeline_state_store.peek_detected_lang() == "en"


# ─────────────────────────────────────────────────────────────────────────────
# _accumulate_voice — helpers for the fake voice module + fake audio
# ─────────────────────────────────────────────────────────────────────────────

def _short_audio():
    # ~0.06s at 16 kHz → below MIN_VOICE_ACCUM_DURATION_SECS (1.5s).
    return [0.0] * 1000


def _long_audio():
    # ~1.9s at 16 kHz → above MIN_VOICE_ACCUM_DURATION_SECS.
    return [0.0] * 30_000


# ── DEBUG=True + refused: entry log (673-674), gate-skipped (721),
#    allowed log (730), exit-refused log (734-736) ────────────────────────────
async def test_accumulate_voice_debug_refused_path(monkeypatch):
    monkeypatch.setattr(_config, "VOICE_BOOTSTRAP_DEBUG", True)
    _wiring._session_store._sync_open_session(
        "av1", "A1", "known", "voice", now=time.time(), now_mono=time.monotonic()
    )
    # No evidence + voice_only_origin=False → replenishment gate skipped + refused.
    await rt._accumulate_voice("av1", _short_audio(), MagicMock())
    assert _wiring._session_store.peek_snapshot("av1") is not None  # returned cleanly


# ── DEBUG=True + replenishment FIRED (703-706) ───────────────────────────────
async def test_accumulate_voice_debug_replenishment_fired(monkeypatch):
    monkeypatch.setattr(_config, "VOICE_BOOTSTRAP_DEBUG", True)
    _wiring._session_store._sync_open_session(
        "av2", "A2", "known", "voice", now=time.time(), now_mono=time.monotonic()
    )
    await _wiring._session_store.set_voice_only_origin("av2", True)  # thin voice-only

    await rt._accumulate_voice("av2", _short_audio(), MagicMock())

    await asyncio.sleep(0.05)  # drain the increment_bootstrap_credits task
    snap = _wiring._session_store.peek_snapshot("av2")
    assert snap.evidence.bootstrap_credits == 1  # replenished +1


# ── DEBUG=True + replenishment SKIPPED-why (mature + at-cap): 707-716 ─────────
async def test_accumulate_voice_debug_replenishment_skipped_reasons(monkeypatch):
    from core.config import (
        VOICE_ACCUM_MATURE_SAMPLE_COUNT, VOICE_MAX_BOOTSTRAP_CREDITS,
    )
    monkeypatch.setattr(_config, "VOICE_BOOTSTRAP_DEBUG", True)
    _wiring._session_store._sync_open_session(
        "av3", "A3", "known", "voice", now=time.time(), now_mono=time.monotonic(),
        bootstrap_credits=VOICE_MAX_BOOTSTRAP_CREDITS,           # at cap → line 714-715
        voice_sample_count=VOICE_ACCUM_MATURE_SAMPLE_COUNT,     # mature → line 712-713
    )
    await _wiring._session_store.set_voice_only_origin("av3", True)

    # Bootstrap credits > 0 → allowed (path=bootstrap); short audio → D3 skip
    # (776-780) after the skipped-why debug block (707-716).
    await rt._accumulate_voice("av3", _short_audio(), MagicMock())
    assert _wiring._session_store.peek_snapshot("av3") is not None


# ── identify self-match → update_voice_heard (751) + voice_self_match src (756)
async def test_accumulate_voice_self_match_updates_voice_heard(monkeypatch):
    monkeypatch.setattr(_config, "VOICE_BOOTSTRAP_DEBUG", False)
    monkeypatch.setattr(
        rt.voice_mod, "identify", AsyncMock(return_value=("av4", 0.9, True))
    )
    # embed stays the stub (→ None) so the function returns at the embed guard.
    _wiring._session_store._sync_open_session(
        "av4", "A4", "known", "voice", now=time.time(), now_mono=time.monotonic(),
        bootstrap_credits=5,
    )

    await rt._accumulate_voice("av4", _long_audio(), MagicMock())

    await asyncio.sleep(0.05)  # drain the update_voice_heard task (751-753)
    snap = _wiring._session_store.peek_snapshot("av4")
    assert snap.evidence.voice_match_conf == pytest.approx(0.9)


# ── DEBUG=True + full added path: embed success → gallery write + exit log 801-803
async def test_accumulate_voice_debug_added_path(monkeypatch):
    monkeypatch.setattr(_config, "VOICE_BOOTSTRAP_DEBUG", True)
    # identify stays the stub (→ no self-match) so path stays "bootstrap"
    # (source = voice_face_verified); embed returns a real vector.
    monkeypatch.setattr(
        rt.voice_mod, "embed", AsyncMock(return_value=[0.1, 0.2, 0.3])
    )

    db = MagicMock()
    db.add_voice_embedding.return_value = True
    db.load_voice_profile_for.return_value = [0.4, 0.5, 0.6]
    db.voice_embedding_count.return_value = 6

    _wiring._session_store._sync_open_session(
        "av5", "A5", "known", "voice", now=time.time(), now_mono=time.monotonic(),
        bootstrap_credits=5,
    )

    await rt._accumulate_voice("av5", _long_audio(), db)

    db.add_voice_embedding.assert_called_once()
    # set_gallery is awaited inside the function (line 794).
    assert _wiring._voice_gallery_store.peek_gallery("av5") == [0.4, 0.5, 0.6]
    assert _wiring._voice_gallery_store.peek_size("av5") == 6

    await asyncio.sleep(0.05)  # drain set_voice_sample_count + decrement tasks
    snap = _wiring._session_store.peek_snapshot("av5")
    assert snap.evidence.voice_sample_count == 6
    assert snap.evidence.bootstrap_credits == 4  # bootstrap credit burned (798)
