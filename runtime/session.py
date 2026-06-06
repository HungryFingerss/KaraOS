# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors
"""runtime/session.py — session lifecycle engine (P1.A1 SP-6.1).

The 5 session-lifecycle functions (_open_session / _voice_accum_allowed /
_close_session / _expire_stale_sessions / _accumulate_voice) + the 5 helpers
they call (_is_disputed / _face_in_frame / _has_recent_face_evidence /
_emit_session_lifecycle_safe / _on_room_end), relocated VERBATIM from
pipeline.py. The lowest engine layer: SP-6.2/6.3/6.4 import session functions
from here (runtime->runtime, acyclic); pipeline.py re-exports them so the
hundreds of existing callers stay byte-identical. Rebound DI state reads via
_wiring._X; reset-stores + lip_tracker from-imported from runtime.wiring.
"""
from __future__ import annotations

import asyncio
import runtime.wiring as _wiring
import time
from core import voice as voice_mod
from core.audio import set_lip_active
from core.config import (
    DISPUTE_AUTO_CLEAR_CONSECUTIVE_TURNS, DISPUTE_AUTO_CLEAR_VOICE_MIN, DISPUTE_AUTO_CLEAR_VOICE_SOLO_MIN, DISPUTE_MAX_DURATION, FACE_LOSS_GRACE, MAX_VOICE_EMBEDDINGS, MIC_SAMPLE_RATE, N_INITIAL_VOICE, N_INITIAL_VOICE_BOOTSTRAP, SCENE_STALE_SECS, VALID_PERSON_TYPES, VOICE_ACCUM_FACE_WITNESS_MAX_AGE_SEC, VOICE_ACCUM_FACE_WITNESS_MIN_CONF, VOICE_ACCUM_MATURE_SAMPLE_COUNT, VOICE_ACCUM_VOICE_SELF_MATCH_MIN, VOICE_RECOGNITION_THRESHOLD, VOICE_SESSION_TIMEOUT,
)
from runtime.wiring import (
    _anti_spoof_rejection_store, _conversation_store, _identity_hints_store, _per_person_agent_store, _presence_store, _query_embedding_store, _track_store, _vision_frame_store, _voice_gallery_store, lip_tracker,
)


def _face_in_frame(pid: str, persons_in_frame: dict) -> bool:
    """Return True only if ``persons_in_frame[pid]`` has a face-sourced entry.

    Voice ID also writes into ``_persons_in_frame`` (to track "who just spoke")
    with ``source="voice"``. Routing, scene, and left-frame logs must not treat
    those as face presence — a voice-only speaker whose pid appears in the dict
    should NOT trigger the "face+voice agree" confident-switch shortcut, and
    should NOT be reported as visibly present in the scene block.

    Bug B (2026-04-20 live run): Chloe (voice-only) was routed through the
    face+voice-agree path and rendered as "[Vision] Chloe — speaking now" in
    the scene block despite never being on camera.
    """
    entry = persons_in_frame.get(pid)
    return entry is not None and entry.get("source") != "voice"
def _has_recent_face_evidence(person_id: str) -> bool:
    """True iff ``_presence_store`` has a recent face-source entry for person_id.

    Voice-only entries (source='voice') do NOT count — distinguishing them is the
    entire point of the Bug B fix (Session 64). Used by the Wave 2 Item 9 heuristic
    to decide whether a thin-gallery known/best_friend session was originally
    voice-only.
    """
    source = _presence_store.peek_source(person_id, "")
    if not source:
        return False
    if source == "voice":
        return False
    last_seen = _presence_store.peek_last_seen(person_id, 0.0)
    return (time.monotonic() - last_seen) < SCENE_STALE_SECS
def _is_disputed(pid_or_session) -> bool:
    """Single source of truth for "is this session in disputed state?".

    Session 73 (Bug D4, 2026-04-22 live run): before this helper, the dispute
    check was scattered across 9 sites in pipeline.py with raw ``==
    "disputed"`` comparisons. Each site independently decided what to do with
    the dispute signal (skip log_turn, skip extraction, refuse KAIROS, label
    the scene, gate privileges, etc.). A new disputed-check is easy to forget
    — the classic "distributed policy = missing policy" antipattern. Routing
    every check through this helper + the grep-invariant source-inspection
    test makes policy drift visible at CI time.

    Accepts either a ``person_id`` (str — looks up ``_session_store.peek_snapshot()``) or
    a pre-fetched session dict (dict — inspects directly). Returns False for
    missing / unknown sessions (fail-open for readers, fail-closed for
    writers: the LLM doesn't accidentally get "disputed" privileges just
    because the session vanished).
    """
    if isinstance(pid_or_session, dict):
        return pid_or_session.get("person_type") == "disputed"
    # Treat None / empty string as "no session" → not disputed.
    if not pid_or_session:
        return False
    _disp_snap = _wiring._session_store.peek_snapshot(pid_or_session)
    return _disp_snap is not None and _disp_snap.person_type == "disputed"
def _open_session(
    person_id: str,
    person_name: str,
    session_type: str,                # "face" | "voice"
    person_type: str,                 # "stranger" | "known" | "best_friend"
    voice_confidence: float = 1.0,
    engagement_gate_passed: bool = False,
) -> None:
    """Open a new session for a person. Idempotent — updates if already open.

    ``person_type`` is a REQUIRED keyword-or-positional arg: every caller must
    commit to which session kind they're opening. Seeding the dict at creation
    time closes the race window where ``_session_store.peek_snapshot(pid).person_type``
    might be absent before the SessionStore task completes after ``_open_session`` —
    with the Step 2 fail-safe "stranger" fallback, that window would mis-gate
    a best_friend as stranger for one iteration.

    ``engagement_gate_passed`` (Step 3): when True, the session was opened
    through a gate that establishes identity (face greeting after anti-spoof,
    or stranger who just cleared the system-name gate). Seeds the voice
    accumulation "bootstrap credits" budget (see _voice_accum_allowed path C)
    so the profile can grow on early turns before face/voice witnesses are
    strong enough. Each successful accumulation decrements the budget.
    """
    if not (person_type in VALID_PERSON_TYPES):
        raise RuntimeError(f'_open_session called with invalid person_type={person_type!r}; must be one of {sorted(VALID_PERSON_TYPES)}')
    now = time.time()                # WALLCLOCK: started_at (enrollment-rename grace, read at :657 via time.time()-started_at) + room id/started_at display
    now_mono = time.monotonic()      # #5 Slice B (§0.1.3 SPLIT): last_face_seen/last_spoke_at staleness seeds (FACE_LOSS_GRACE / VOICE_SESSION_TIMEOUT)
    existing = _wiring._session_store.peek_snapshot(person_id)
    if existing is not None:
        # P0.7.3: named lifecycle call covers last_spoke_at, last_face_seen, voice_confidence
        try:
            _loop = asyncio.get_running_loop()
            _loop.create_task(_wiring._session_store.update_on_reopen(
                person_id, voice_confidence=voice_confidence, now=now_mono))  # #5 Slice B: last_face_seen/last_spoke_at staleness → mono
        except RuntimeError:
            pass  # OPTIONAL: no running loop in test/early-boot context
        # Don't overwrite person_type on re-open — caller may have promoted
        # stranger→known via update_person_name since the last open.
    else:
        from collections import deque as _deque
        # Session 111 Critical #5 — reset the per-person EmotionAgent on
        # every fresh session so the 3-turn rolling window can't carry
        # yesterday's emotions into today. Agents are owned by
        # _per_person_agent_store; pop is cheap (object will be lazily
        # recreated on first emotion-detection call in conversation_turn).
        try:
            _loop = asyncio.get_running_loop()
            _loop.create_task(_per_person_agent_store.pop_emotion_agent(person_id))
        except RuntimeError:
            # No running event loop (test context / early boot) — run synchronously
            # so the invariant holds immediately and sync test assertions pass.
            try:
                asyncio.run(_per_person_agent_store.pop_emotion_agent(person_id))
            except Exception:
                pass  # CLEANUP: pop is best-effort
        # Session 112 Part 1 — room-session lifecycle. Mint a new
        # room_session_id on the FIRST open into an empty room; later
        # opens (another person joining) inherit the existing id. The
        # room stays alive until _close_session empties the session
        # table (see _close_session for the end-of-room hook).
        _current_room_session = _wiring._pipeline_state_store.peek_active_room_session()
        if _current_room_session is None:
            import uuid as _uuid_rs
            _current_room_session = f"room_{int(now)}_{_uuid_rs.uuid4().hex[:6]}"
            # Phase 3B.1 — stamp wall-clock start time so <<<ROOM>>> block
            # can render duration. Must be set in the SAME branch that
            # mints the id so the pair stays consistent.
            # Phase 3B.6 — fresh participants set for the new room.
            # Set synchronously via private helper so that callers
            # reading peek_active_room_session() immediately after _open_session()
            # see the minted id without waiting for a create_task to drain.
            # Same atomicity contract as _close_session's synchronous clear.
            _wiring._pipeline_state_store._sync_mint_room(_current_room_session, now)
            print(f"[Room] New room session: {_current_room_session}")
        # Phase 3B.6 — accumulate every pid that joins this room so
        # synthesize_room has the participant list at room-end time
        # (when _session_store has no active sessions). Idempotent on re-open.
        # Session 116 P1 #9 — log room join events explicitly so an
        # outside reviewer can audit room membership transitions
        # without inferring from open/close lines.
        _current_room_participants = _wiring._pipeline_state_store.peek_active_room_participants()
        _was_new = person_id not in _current_room_participants
        # Add participant synchronously via private helper for immediate
        # visibility to callers reading peek_active_room_participants() right
        # after _open_session() returns.
        _wiring._pipeline_state_store._sync_add_room_participant(person_id)
        if _was_new:
            print(
                f"[Room] Participant joined: {person_name} ({person_id}) "
                f"\u2192 {_current_room_session} "
                f"(now {len(_current_room_participants) + 1} participant(s))"
            )
        print(f"[Session] Open: {person_id} ({session_type}) — {person_name}")
        _bootstrap = N_INITIAL_VOICE_BOOTSTRAP if engagement_gate_passed else 0
        # Bug A Part 1: hydrate voice_sample_count from a DB-authoritative count
        # so a re-opened session carries forward its prior voice samples.
        # Without this, a voice-only stranger whose session expired (VOICE_SESSION_TIMEOUT)
        # would restart at sample 0 and never reach maturity (Path B needs 5+).
        #
        # Obs 1 (2026-04-20 post-review): prefer the live DB count over the
        # in-memory cache. The cache can go stale when a delete_person()
        # call from the dashboard/CLI removes voice_embeddings rows out of
        # process. If cache and DB disagree, repair the cache so other consumers
        # (e.g. _effective_switch_threshold gating) see the correct number too.
        # Face-side evidence stays ephemeral — it must be re-established each session.
        _db_voice_count = _voice_gallery_store.peek_size(person_id, 0)
        if _wiring._face_db_ref is not None:
            try:
                _db_voice_count = _wiring._face_db_ref.count_voice_embeddings(person_id)
                if _voice_gallery_store.peek_size(person_id, -1) != _db_voice_count:
                    _existing_emb = _voice_gallery_store.peek_gallery(person_id)
                    if _existing_emb is not None:
                        try:
                            _loop = asyncio.get_running_loop()
                            _loop.create_task(_voice_gallery_store.set_gallery(person_id, _existing_emb, _db_voice_count))
                        except RuntimeError:
                            pass
            except Exception:
                pass  # OPTIONAL: cache fallback already seeded above — stale count safe until next session open
        # Canary #4 B1 (2026-05-31): register the session SYNCHRONOUSLY so peek_snapshot /
        # peek_all_snapshots see it the instant _open_session returns. The old fire-and-forget
        # create_task left it invisible to the very next voice-first re-check (:7684), which
        # then ran the stranger engagement gate even after a known speaker was identified —
        # dropping the turn (no system name) or spawning a phantom visitor (system name).
        # _sync_open_session is the one blessed sync write (atomic construct-then-insert, no
        # await — see SessionStore docstring); it needs no running loop, so the old
        # create_task / get_running_loop / except-RuntimeError dance is gone (the session now
        # also opens in test/early-boot contexts that previously had no loop to schedule on).
        _wiring._session_store._sync_open_session(
            person_id, person_name, person_type, session_type,
            now=now, now_mono=now_mono,
            bootstrap_credits=_bootstrap,
            room_session_id=_current_room_session,
            voice_sample_count=_db_voice_count,
        )
        # Wave 4 Item 18 — fetch core memory at session open so render_session_stable_prefix
        # can inject it into Section 2 without a DB call on every turn.
        _core_mem_value: list = []
        if _wiring._brain_orchestrator is not None:
            try:
                _bf_row_open = _wiring._face_db_ref.get_best_friend() if _wiring._face_db_ref else None
                _bf_id_open  = _bf_row_open["id"] if _bf_row_open else None
                _core_mem_value = _wiring._brain_orchestrator.brain_db.get_core_memory_for(
                    requester_pid  = person_id,
                    best_friend_id = _bf_id_open,
                    entity         = person_name,
                )
            except Exception as _cm_err:
                print(f"[Session] core_memory fetch failed for {person_id}: {_cm_err!r}")
        # P0.7.3: named lifecycle call (uses local _core_mem_value — no dict read)
        try:
            _loop = asyncio.get_running_loop()
            _loop.create_task(_wiring._session_store.set_core_memory(
                person_id, _core_mem_value))
        except RuntimeError:
            pass  # OPTIONAL: no running loop in test/early-boot context
        # Wave 2 Item 9: backfill heuristic for pre-S120 promoted voice-only strangers.
        # S120 set voice_only_origin=True at the engagement-gate pass for new promotions.
        # Pre-S120 promoted persons have voice_only_origin=False and no way to grow their
        # gallery (bootstrap replenishment was gated on person_type=='stranger', which
        # becomes False the moment update_person_name fires). Infer the flag retroactively
        # when: not already True, person is known/best_friend (not disputed/stranger),
        # gallery is still thin (< N_INITIAL_VOICE), and no face evidence is currently
        # available (confirming this is a voice-only session). Idempotent across re-opens.
        if (
            not (_wiring._session_store.peek_snapshot(person_id).voice_only_origin if _wiring._session_store.peek_snapshot(person_id) is not None else False)
            and person_type in ("known", "best_friend")
            and _voice_gallery_store.peek_size(person_id, 0) < N_INITIAL_VOICE
            and not _has_recent_face_evidence(person_id)
        ):
            print(
                f"[Backfill] {person_name} ({person_id}) — voice_only_origin=True inferred "
                f"(person_type={person_type}, "
                f"voice_n={_voice_gallery_store.peek_size(person_id, 0)}, no face)"
            )
            try:
                _loop = asyncio.get_running_loop()
                _loop.create_task(_wiring._session_store.set_voice_only_origin(person_id, True))
            except RuntimeError:
                pass  # OPTIONAL: no running loop in test/early-boot context

    # P0.0.7 H11 — emit session_lifecycle=open event via the shared helper.
    _h11_room_open = _wiring._pipeline_state_store.peek_active_room_session()
    _emit_session_lifecycle_safe(
        lifecycle="open",
        person_id=person_id,
        person_name=person_name,
        source=session_type,
        person_type=person_type,
        room_session_id=_h11_room_open,
    )
def _emit_session_lifecycle_safe(
    *,
    lifecycle: str,
    person_id: str,
    person_name: "str | None",
    source: str,
    person_type: str,
    room_session_id: "str | None",
) -> None:
    """P0.0.7 H11 single producer location for session_lifecycle events.

    Called by both _open_session (lifecycle='open') and _close_session
    (lifecycle='close') so D7 N=1 holds. Delegates to `safe_emit_sync`
    (single P0.4-annotated except lives in the helper).
    """
    from core.event_log import safe_emit_sync, SessionLifecyclePayload
    safe_emit_sync(
        "session_lifecycle",
        SessionLifecyclePayload(
            lifecycle=lifecycle,
            person_id=person_id,
            person_name=person_name,
            source=source,
            person_type=person_type,
            room_session_id=room_session_id,
        ),
        session_id=person_id,
        room_session_id=room_session_id,
    )
def _voice_accum_allowed(pid: str) -> tuple[bool, str, str]:
    """Decide whether voice accumulation is allowed for a session.

    Returns (allowed, reason, path). ``path`` is one of ``"face_witness"``,
    ``"voice_self_match"``, ``"bootstrap"``, or ``"refused"``. Paths are tried
    in that order — first-match wins. No hardcoded thresholds; all values come
    from config so tuning is a single knob per concern.
    """
    snap = _wiring._session_store.peek_snapshot(pid)
    ev = snap.evidence if snap is not None else None
    # #5 Slice D §1.4/§3.D: monotonic to match the now-monotonic VoiceEvidence.face_last_seen_ts
    # (Slice A/B flipped the `update_face_seen(ts=)` writer arg). face_age = mono_now - mono_field
    # is consistent elapsed-math; `now` feeds ONLY Path-A face_age (no persist/display) -> straight
    # flip. Was `time.time()` -> +1.78e9 garbage face_age -> Path A never fired (the read-half of
    # the deferral test_voice_accum_observability.py:7-9 named).
    now = time.monotonic()

    if ev is None:
        return (False, "no session", "refused")

    # Path A — recent confident face witness
    face_age = now - ev.face_last_seen_ts
    if (ev.face_match_conf >= VOICE_ACCUM_FACE_WITNESS_MIN_CONF
            and ev.anti_spoof_live
            and face_age <= VOICE_ACCUM_FACE_WITNESS_MAX_AGE_SEC):
        return (True,
                f"face witness (conf={ev.face_match_conf:.2f}, age={face_age:.1f}s)",
                "face_witness")

    # Path B — mature voice profile self-matching
    if (ev.voice_match_conf >= VOICE_ACCUM_VOICE_SELF_MATCH_MIN
            and ev.voice_sample_count >= VOICE_ACCUM_MATURE_SAMPLE_COUNT):
        return (True,
                f"voice self-match (conf={ev.voice_match_conf:.2f}, "
                f"n={ev.voice_sample_count})",
                "voice_self_match")

    # Path C — bootstrap credits from engagement gate
    if ev.bootstrap_credits > 0:
        return (True,
                f"bootstrap ({ev.bootstrap_credits} credits remaining)",
                "bootstrap")

    return (False,
            f"no witness (face_conf={ev.face_match_conf:.2f}, "
            f"age={face_age:.1f}s, voice_n={ev.voice_sample_count}, "
            f"voice_conf={ev.voice_match_conf:.2f}, "
            f"bootstrap={ev.bootstrap_credits})",
            "refused")
async def _on_room_end(
    room_session_id: str,
    speaker_pids: "list[str] | None" = None,
    started_at: "float | None" = None,
) -> None:
    """P0.S7.D-D Stage 1 shim → RoomOrchestrator.on_room_end (async)."""
    if _wiring._room_orchestrator is None:
        raise RuntimeError(
            "RoomOrchestrator not initialized — _init_room_orchestrator() "
            "must run first (production: from run(); tests: autouse fixture)"
        )
    await _wiring._room_orchestrator.on_room_end(room_session_id, speaker_pids, started_at)
def _close_session(person_id: str) -> None:
    """Close and remove a person's session."""
    _close_snap = _wiring._session_store.peek_snapshot(person_id)
    _pname_log = _close_snap.person_name if _close_snap is not None else person_id
    print(f"[Session] Close: {person_id} — {_pname_log}")
    # Session 97 Fix 2: if this is a stranger session that accumulated
    # no usable data (gate-blocked at open and never spoke to the
    # accumulator), prune the row immediately instead of waiting for
    # the 7-day TTL. The FaceDB method does its own triple-check —
    # person_type=='stranger', zero voice embeddings, zero conversation
    # turns — so a genuine short-interaction stranger with even ONE
    # preserved signal survives until the TTL.
    _sess_pt_close = _close_snap.person_type if _close_snap is not None else None
    if _sess_pt_close == "stranger" and _wiring._face_db_ref is not None:
        try:
            _wiring._face_db_ref.prune_zero_value_stranger(person_id)
        except Exception as _prune_ex:
            print(f"[Session] zero-value prune failed for {person_id}: {_prune_ex!r}")
    # Follow-up #129 (C4): the blessed SYNC close — the session is removed the instant this
    # returns, so the room-end gate below (and the line-2379 full-cleanup in
    # _expire_stale_sessions) read true post-removal state. Closes the simultaneous-multi-
    # expiry room-end race (the close-side mirror of Canary #4 B1's sync open). A sync pop
    # needs no running loop, so no try/except. The async close_session() delegates to this
    # same method (C2) so the two removal paths cannot diverge.
    _wiring._session_store._sync_close_session(person_id)
    try:
        _loop = asyncio.get_running_loop()
        _loop.create_task(_per_person_agent_store.discard_session_started(person_id))
    except RuntimeError:
        pass  # OPTIONAL: no running loop in test/early-boot context
    # Clean up track store entries for this session
    try:
        _loop = asyncio.get_running_loop()
        # P0.S1 Phase 3 cleanup — capture track_ids BEFORE pruning so the
        # anti-spoof rejection store can pop the matching keys. Without
        # this, a returning user re-using the same track_id would inherit
        # the prior session's rejection window count.
        _tids_to_release = list(_track_store.peek_tracks_for_person(person_id))
        _stranger_tid = _track_store.peek_track_for_stranger_pid(person_id)
        if _stranger_tid is not None:
            _tids_to_release.append(_stranger_tid)
        _loop.create_task(_track_store.prune_for_session_close(person_id))
        for _tid in _track_store.peek_tracks_for_person(person_id):
            _loop.create_task(_track_store.remove_track(_tid))
        for _tid in _tids_to_release:
            # Per-track scope (C2) — pop rejection history for this track.
            _loop.create_task(_anti_spoof_rejection_store.pop(str(_tid)))
    except RuntimeError:
        pass  # OPTIONAL: no running loop in test/early-boot context
    # Evict per-person caches so re-entry never hits stale data
    try:
        _loop = asyncio.get_running_loop()
        _loop.create_task(_query_embedding_store.discard(person_id))
        _loop.create_task(_identity_hints_store.discard(person_id))
    except RuntimeError:
        pass  # OPTIONAL: no running loop in test/early-boot context
    # Clear any identity-dispute flag with the orchestrator — the session is
    # gone, so next time this pid appears it's a fresh start.
    if _wiring._brain_orchestrator:
        _wiring._brain_orchestrator.clear_disputed(person_id)

    # Session 112 Part 3 — presence store session-scoped cleanup.
    # Previously entries lingered until SCENE_STALE_SECS aged them out
    # (30s), producing a window where the scene block still rendered
    # people whose sessions had already closed. Remove immediately on
    # session close. If they're physically present, next background
    # face scan re-adds them (correct — they're visible). If they've
    # actually left the room, the lingering entry is removed right
    # away. Resolves the scene-contradicts-session-state class of bug.
    try:
        _loop = asyncio.get_running_loop()
        _loop.create_task(_presence_store.remove(person_id))
    except RuntimeError:
        pass  # OPTIONAL: no running loop in test/early-boot context

    # Session 112 Part 1 — room-session end hook. When this close
    # empties the active_sessions table, the room is over. Fire
    # fire-and-forget synthesis tasks (current 3A scope: just log
    # the room end + clear the id; 3B will hook room-level insight,
    # relationship update, cross-person safety scan here).
    #
    # NOTE (#129 Q2): close is now SYNCHRONOUS via `_sync_close_session`, so this person's
    # session is already gone when this gate runs. The `s.person_id != person_id` exclusion
    # below is retained as belt-and-braces for any future caller that reaches this gate
    # without sync-removing first. The room ends when this IS the last person: on
    # simultaneous multi-expiry, the earlier sessions are already removed when the last one
    # closes → the last close sees an empty remainder and fires room-end exactly once.
    _room_snap = _wiring._pipeline_state_store.peek_active_room_session()
    _remaining_sessions = [s for s in _wiring._session_store.peek_all_snapshots()
                           if s.person_id != person_id]
    if not _remaining_sessions and _room_snap is not None:
        _ended_room        = _room_snap
        _ended_started_at  = _wiring._pipeline_state_store.peek_active_room_started_at()
        _ended_participants = list(_wiring._pipeline_state_store.peek_active_room_participants())
        # Clear room fields synchronously so the second _close_session in the
        # same event-loop tick sees _active_room_session=None and does NOT
        # fire a second room-end (the original module-level variable was
        # cleared immediately; the store must mirror that atomicity).
        # The lock is not needed here: this is a single-threaded asyncio
        # context and CPython GIL protects the simple assignments.
        _wiring._pipeline_state_store._sync_clear_room()
        print(f"[Room] Room session ended: {_ended_room}")
        # Guard against sync-test contexts where no event loop is
        # running — `asyncio.create_task` would raise/warn outside
        # an active loop. If the hook can't be scheduled, log it
        # without blocking the close path.
        try:
            asyncio.get_running_loop()
            asyncio.create_task(
                _on_room_end(_ended_room, _ended_participants, _ended_started_at)
            )
        except RuntimeError:
            print(f"[Room] Room-end hook skipped for {_ended_room} — no running loop")

    # P0.0.7 H11 — emit session_lifecycle=close via the shared helper.
    # Writer task's _flush_one detects the close-event after persisting
    # it and calls _clear_session_parents — i.e., the close event itself
    # still has access to its parent-event-id chain at persist time, and
    # the cache clears only AFTER the close row is durable.
    _emit_session_lifecycle_safe(
        lifecycle="close",
        person_id=person_id,
        person_name=_pname_log,
        source=(_close_snap.session_type if _close_snap is not None else ""),
        person_type=(_close_snap.person_type if _close_snap is not None else ""),
        room_session_id=(_close_snap.room_session_id if _close_snap is not None else None),
    )
def _expire_stale_sessions() -> bool:
    """Expire timed-out sessions and clean up per-person state.

    Called from both the outer WATCHING loop AND the inner conversation loop
    so zombie sessions (e.g. abandoned voice-only strangers) are cleaned up
    within VOICE_SESSION_TIMEOUT even during active conversations.

    Returns True if any session was closed.
    """
    _now_fl = time.time()                    # WALLCLOCK: persisted dispute_set_at re-anchor (watchdog display :4429)
    _now_fl_mono = time.monotonic()          # #5 Slice B (§0.1.3 SPLIT): elapsed-math reads (FACE_LOSS_GRACE / VOICE_SESSION_TIMEOUT / DISPUTE_MAX_DURATION)
    _expired: list[str] = []
    for _snap in _wiring._session_store.peek_all_snapshots():
        # Identity-disputed sessions get a hard cap — vision keeps matching the
        # wrong person so `last_face_seen` never stales out via FACE_LOSS_GRACE.
        # Force-close after DISPUTE_MAX_DURATION so pollution has a bounded tail.
        # Finding K — if a future path sets person_type="disputed" without also
        # setting dispute_set_at, lazily anchor it here on the first check so the
        # timeout still fires (instead of permanently resetting to now each pass).
        if _is_disputed(_snap.person_id):
            # #5 Slice B (§0.1.3 SPLIT): DISPUTE_MAX_DURATION is elapsed-math → read the
            # monotonic companion. Wall dispute_set_at is retained for the persisted watchdog
            # display (:4429). The defensive re-anchor stamps BOTH (wall via _now_fl + mono via
            # _now_fl_mono) so a re-anchored dispute reads fresh on the mono timeout side too.
            _dispute_start_mono = _snap.dispute_set_at_monotonic
            if _dispute_start_mono is None:
                try:
                    _loop = asyncio.get_running_loop()
                    _loop.create_task(_wiring._session_store.set_dispute_set_at(
                        _snap.person_id, _now_fl, ts_monotonic=_now_fl_mono))
                except RuntimeError:
                    asyncio.run(_wiring._session_store.set_dispute_set_at(
                        _snap.person_id, _now_fl, ts_monotonic=_now_fl_mono))  # OPTIONAL: sync fallback
                _dispute_start_mono = _now_fl_mono

            # Bug D1 (2026-04-22 live run): signal-based dispute auto-clear.
            # Previously disputes only cleared via DISPUTE_MAX_DURATION=180s —
            # 60% of a 5-minute demo broken when the LLM wrongly triggered
            # report_identity_mismatch.
            #
            # Session 73 post-review Medium C2: voice auto-clear trusts the
            # same sensor that triggered the dispute. Without face
            # corroboration, raise the bar to DISPUTE_AUTO_CLEAR_VOICE_SOLO_MIN
            # (0.85 — near-confirmed biometric match) so a wrongly-cleared
            # dispute requires a very strong signal. When face is co-present
            # (stronger corroboration via separate modality), the lower
            # DISPUTE_AUTO_CLEAR_VOICE_MIN (0.70) is acceptable. Restore via
            # prior_person_type (captured at dispute-flip).
            _ev = _snap.evidence
            _pif_view = {s.person_id: {"source": s.source} for s in _presence_store.peek_all_snapshots()}
            _face_confirmed = (
                _face_in_frame(_snap.person_id, _pif_view)
                and _ev.face_match_conf >= DISPUTE_AUTO_CLEAR_VOICE_MIN
            )
            _voice_floor = (
                DISPUTE_AUTO_CLEAR_VOICE_MIN
                if _face_confirmed
                else DISPUTE_AUTO_CLEAR_VOICE_SOLO_MIN
            )
            _recent_vc = _snap.recent_voice_confs
            _voice_confirmed = (
                len(_recent_vc) >= DISPUTE_AUTO_CLEAR_CONSECUTIVE_TURNS
                and all(
                    _c >= _voice_floor
                    for _c in list(_recent_vc)[-DISPUTE_AUTO_CLEAR_CONSECUTIVE_TURNS:]
                )
            )
            if _voice_confirmed or _face_confirmed:
                _reason = (
                    f"{DISPUTE_AUTO_CLEAR_CONSECUTIVE_TURNS} consecutive strong "
                    f"voice matches (≥{_voice_floor})"
                    + (" [face-corroborated]" if _face_confirmed else " [voice-only]")
                    if _voice_confirmed else
                    f"face in frame with face_match_conf≥{DISPUTE_AUTO_CLEAR_VOICE_MIN}"
                )
                # Session 73 post-review Critical #2: fail-closed fallback.
                # If a future dispute-flip path forgets to capture
                # prior_person_type, defaulting to "known" here would
                # silently promote a stranger session — privilege escalation.
                # "stranger" is the safer fallback; worst case is the session
                # loses best_friend privileges but a user re-auth via
                # engagement gate restores them on the next turn.
                _restore_type = _snap.prior_person_type or "stranger"
                # P0.7.3: atomic named call (handles person_type restore + all dispute fields)
                try:
                    _loop = asyncio.get_running_loop()
                    _loop.create_task(_wiring._session_store.clear_dispute(_snap.person_id, now=_now_fl))
                except RuntimeError:
                    asyncio.run(_wiring._session_store.clear_dispute(_snap.person_id, now=_now_fl))  # OPTIONAL: sync fallback
                if _wiring._brain_orchestrator:
                    _wiring._brain_orchestrator.clear_disputed(_snap.person_id)
                print(
                    f"[Dispute] Auto-cleared for {_snap.person_name} — "
                    f"{_reason}; restored person_type={_restore_type!r}"
                )
                # Session no longer disputed — fall through to normal session
                # expiry checks below (not `continue`, so we don't skip them).
            elif _now_fl_mono - _dispute_start_mono > DISPUTE_MAX_DURATION:
                print(
                    f"[Pipeline] Dispute timeout for {_snap.person_name} — "
                    f"force-closing after {_now_fl_mono - _dispute_start_mono:.0f}s"
                )
                _expired.append(_snap.person_id)
                continue
        if _snap.session_type == "face":
            if _now_fl_mono - _snap.last_face_seen > FACE_LOSS_GRACE:
                _expired.append(_snap.person_id)
        else:  # voice-started
            if _now_fl_mono - _snap.last_spoke_at > VOICE_SESSION_TIMEOUT:
                _expired.append(_snap.person_id)

    for _pid in _expired:
        _snap_exp = _wiring._session_store.peek_snapshot(_pid)
        if _snap_exp is None:
            continue
        _pname = _snap_exp.person_name
        print(f"[Pipeline] Session expired: {_pname} ({_pid})")
        try:
            _loop_exp = asyncio.get_running_loop()
            _loop_exp.create_task(_conversation_store.pop_history(_pid))
            _loop_exp.create_task(_conversation_store.touch_greeted(_pid, time.monotonic()))
        except RuntimeError:
            asyncio.run(_conversation_store.pop_history(_pid))  # OPTIONAL: sync fallback
            asyncio.run(_conversation_store.touch_greeted(_pid, time.monotonic()))  # OPTIONAL: sync fallback
        if _wiring._brain_orchestrator:
            _wiring._brain_orchestrator.notify_session_end(_pid)
        _close_session(_pid)
        _vision_frame_store._sync_set_prev_det_count(0)

    if _expired and not _wiring._session_store.peek_all_snapshots():
        # All sessions closed — full cleanup
        lip_tracker.reset()
        set_lip_active(False)
        try:
            _loop = asyncio.get_running_loop()
            _loop.create_task(_presence_store.clear())
        except RuntimeError:
            pass  # OPTIONAL: no running loop in test/early-boot context
        try:
            asyncio.get_running_loop().create_task(_wiring._pipeline_state_store.set_detected_lang("en"))
        except RuntimeError:
            asyncio.run(_wiring._pipeline_state_store.set_detected_lang("en"))

    return bool(_expired)
async def _accumulate_voice(
    person_id:     str,
    audio:         "np.ndarray",
    db:            "FaceDB",
    face_verified: bool  = False,   # kept for compat; evidence-dict is authoritative now
    min_self_match: float = 0.35,
) -> None:
    """Voice accumulation policy — gated by _voice_accum_allowed().

    Three allowed paths (config-tuned, not hardcoded here):
      A) face witness   — recent confident face + anti-spoof live
      B) voice match    — mature self-match on an already-grown profile
      C) bootstrap      — engagement-gate credits burning down on early turns

    When all three fail, accumulation is refused and the session won't grow
    its voice profile until better evidence arrives.
    """
    loop    = asyncio.get_running_loop()
    _acc_snap = _wiring._session_store.peek_snapshot(person_id)

    # Session 94 Fix #5 — bootstrap credit replenishment. When an engagement-
    # gated stranger (said the system name earlier, ``waiting_for_name=False``)
    # has burned all initial bootstrap credits but hasn't yet reached voice
    # profile maturity (Path B threshold), top up 1 credit per turn up to
    # VOICE_MAX_BOOTSTRAP_CREDITS. Without this, a stranger whose session
    # expires and re-opens via voice match inherits bootstrap=0 from the
    # ``_open_session`` default (no engagement_gate_passed=True on re-open
    # path), and every subsequent accumulation refuses — profile frozen.
    # Observed 2026-04-22 live run: stranger stuck at voice_n=2 across
    # multiple visits despite passing engagement gates each time.
    from core.config import (
        VOICE_BOOTSTRAP_REPLENISH_ENABLED, VOICE_MAX_BOOTSTRAP_CREDITS,
        VOICE_BOOTSTRAP_DEBUG,
    )
    # F2 diagnostic — log entry state before replenishment decision.
    if VOICE_BOOTSTRAP_DEBUG:
        _ev_pre = _acc_snap.evidence if _acc_snap is not None else None
        print(
            f"[Voice-Debug] _accumulate_voice entry: pid={person_id} "
            f"voice_only_origin={_acc_snap.voice_only_origin if _acc_snap is not None else False} "
            f"waiting_for_name={_acc_snap.waiting_for_name if _acc_snap is not None else False} "
            f"bootstrap_pre={_ev_pre.bootstrap_credits if _ev_pre is not None else 0} "
            f"voice_n={_ev_pre.voice_sample_count if _ev_pre is not None else 0}"
        )
    # S120 #1/#2 — condition widened from person_type=="stranger" to
    # voice_only_origin flag. A voice-only person promoted from stranger →
    # known loses person_type=="stranger" the moment update_person_name fires,
    # which previously froze their voice profile permanently at whatever
    # voice_n they had reached. The flag survives promotion and drives
    # replenishment until the profile matures or a face is witnessed.
    # F2 fix: default changed from True → False. known/best_friend sessions
    # don't carry waiting_for_name at all; defaulting to True caused
    # replenishment to always skip for every non-stranger voice-only session.
    if (VOICE_BOOTSTRAP_REPLENISH_ENABLED
            and (_acc_snap.voice_only_origin if _acc_snap is not None else False)
            and not (_acc_snap.waiting_for_name if _acc_snap is not None else False)):
        _snap_rep = _wiring._session_store.peek_snapshot(person_id)
        _ev_rep = _snap_rep.evidence if _snap_rep is not None else None
        voice_n = _ev_rep.voice_sample_count if _ev_rep is not None else 0
        current_credits = _ev_rep.bootstrap_credits if _ev_rep is not None else 0
        if (voice_n < VOICE_ACCUM_MATURE_SAMPLE_COUNT
                and current_credits < VOICE_MAX_BOOTSTRAP_CREDITS):
            loop.create_task(_wiring._session_store.increment_bootstrap_credits(
                person_id, cap=VOICE_MAX_BOOTSTRAP_CREDITS,
            ))
            if VOICE_BOOTSTRAP_DEBUG:
                print(
                    f"[Voice-Debug] Replenishment FIRED for {person_id} "
                    f"→ bootstrap≈{min(current_credits + 1, VOICE_MAX_BOOTSTRAP_CREDITS)}"
                )
        elif VOICE_BOOTSTRAP_DEBUG:
            # Log WHY replenishment was skipped.
            _reasons = []
            if not (_acc_snap.voice_only_origin if _acc_snap is not None else False):
                _reasons.append("voice_only_origin=False")
            if _ev_rep is not None and _ev_rep.voice_sample_count >= VOICE_ACCUM_MATURE_SAMPLE_COUNT:
                _reasons.append(f"already_mature(voice_n={_ev_rep.voice_sample_count})")
            if _ev_rep is not None and _ev_rep.bootstrap_credits >= VOICE_MAX_BOOTSTRAP_CREDITS:
                _reasons.append(f"at_cap(credits={_ev_rep.bootstrap_credits})")
            print(
                f"[Voice-Debug] Replenishment SKIPPED for {person_id}: "
                f"{', '.join(_reasons) if _reasons else 'condition_gate_false'}"
            )
    elif VOICE_BOOTSTRAP_DEBUG:
        print(
            f"[Voice-Debug] Replenishment gate skipped for {person_id}: "
            f"REPLENISH_ENABLED={VOICE_BOOTSTRAP_REPLENISH_ENABLED} "
            f"voice_only_origin={_acc_snap.voice_only_origin if _acc_snap is not None else False} "
            f"waiting_for_name={_acc_snap.waiting_for_name if _acc_snap is not None else False}"
        )

    allowed, reason, path = _voice_accum_allowed(person_id)
    if VOICE_BOOTSTRAP_DEBUG:
        print(f"[Voice-Debug] _voice_accum_allowed for {person_id}: {path} / allowed={allowed} ({reason})")
    if not allowed:
        print(f"[Voice] Refused accumulation for {person_id}: {reason}")
        if VOICE_BOOTSTRAP_DEBUG:
            _snap_exit = _wiring._session_store.peek_snapshot(person_id)
            _ev_exit = _snap_exit.evidence if _snap_exit is not None else None
            print(
                f"[Voice-Debug] _accumulate_voice exit (refused): pid={person_id} "
                f"bootstrap_post={_ev_exit.bootstrap_credits if _ev_exit is not None else 0}"
            )
        return

    # Spec 2 Phase A (A4): name the chosen accumulation path so the next canary's log
    # shows which path filled (or failed to fill) the gallery. (Refused is logged above.)
    print(f"[Voice] accum path for {person_id}: {path}")

    v_pid, v_score, _ = await voice_mod.identify(
        audio, _voice_gallery_store.peek_all_gallery(), VOICE_RECOGNITION_THRESHOLD
    )
    # Track the latest voice self-match in evidence regardless of accumulation outcome.
    if v_pid == person_id and v_score > 0.0:
        loop.create_task(_wiring._session_store.update_voice_heard(
            person_id, conf=v_score, ts=time.monotonic(),   # #5 Slice B: last_spoke_at (VOICE_SESSION_TIMEOUT elapsed-math)
        ))

    if v_pid == person_id and v_score >= min_self_match:
        source = "voice_self_match"
    elif path in ("face_witness", "bootstrap"):
        source = "voice_face_verified"
    else:
        # Spec 2 Phase A (A2): stop failing silently — log the Path-B weak-self-match skip.
        print(
            f"[Voice] accum skip {person_id}: Path-B self-match weak "
            f"(v_pid={v_pid!r}, v_score={v_score:.3f} < {min_self_match}, path={path})"
        )
        return  # Path B said OK but self-match weak — skip this sample

    # P0.S7.5.2 D3 — minimum-utterance-duration gate. ECAPA-TDNN embeddings
    # below ~1.5s are unreliable (per core/voice.py:147); short-utterance
    # noise drifts the gallery centroid over time (canary 3 2026-05-20:
    # Jagan's mature profile scoring 0.3-0.4 on his own utterances).
    # Verbose-by-design skip log per Plan v2 §6 — canary 4 needs the
    # diagnostic data to validate D3 against real audio durations.
    from core.config import MIN_VOICE_ACCUM_DURATION_SECS as _D3_MIN_SECS
    _audio_duration_secs = float(len(audio)) / MIC_SAMPLE_RATE if hasattr(audio, "__len__") else 0.0
    if _audio_duration_secs < _D3_MIN_SECS:
        print(
            f"[Voice] Skipped accum for {person_id}: short utterance "
            f"{_audio_duration_secs:.2f}s < {_D3_MIN_SECS}s"
        )
        return

    emb = await voice_mod.embed(audio)
    if emb is None:
        # Spec 2 Phase A (A1): stop failing silently — log the embed-failure skip.
        print(f"[Voice] accum skip {person_id}: embed returned None")
        return
    added = await loop.run_in_executor(
        None, db.add_voice_embedding, person_id, emb, source, v_score
    )
    if added:
        updated = await loop.run_in_executor(None, db.load_voice_profile_for, person_id)
        count = await loop.run_in_executor(None, db.voice_embedding_count, person_id)
        if updated is not None:
            await _voice_gallery_store.set_gallery(person_id, updated, count)
        # Update evidence: sample count grew; if this was a bootstrap grant, burn a credit.
        loop.create_task(_wiring._session_store.set_voice_sample_count(person_id, count))
        if path == "bootstrap":
            loop.create_task(_wiring._session_store.decrement_bootstrap_credits(person_id))
        print(f"[Voice] Profile updated for {person_id} ({count}/{MAX_VOICE_EMBEDDINGS} voice samples) [via {path}]")
        if VOICE_BOOTSTRAP_DEBUG:
            _snap_added = _wiring._session_store.peek_snapshot(person_id)
            _ev_added = _snap_added.evidence if _snap_added is not None else None
            print(
                f"[Voice-Debug] _accumulate_voice exit (added): pid={person_id} "
                f"bootstrap_post={_ev_added.bootstrap_credits if _ev_added is not None else 0} "
                f"voice_n={_ev_added.voice_sample_count if _ev_added is not None else 0}"
            )
