"""runtime/context_blocks.py — Multispeaker transcript + scene-candidate count + zone geometry (pure; scene-block render/cache defers to SP-5).

Extracted VERBATIM from pipeline.py (P1.A1 SP-4 — pure leaves).
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

from core.brain_agent import _infer_location_zone as _brain_infer_zone

import asyncio

import core.state as state
import runtime.wiring as _wiring
from core.cache_store import CACHE_MISS
from core.config import (
    VOICE_ROUTING_FACE_STALE_SECS,
    SCENE_STALE_SECS, SCENE_VOICE_STALE, SCENE_VISITOR_RECENCY_SECS,
    SCENE_BLOCK_CACHE_ENABLED,
)
from runtime.state_enums import PipelineState
from runtime.session import _is_disputed
from runtime.wiring import _scene_block_store


def _infer_zone(bbox: tuple, frame_w: int, frame_h: int) -> str:
    """Map a face bounding box to a zone label using the shared brain_agent helper."""
    x1, y1, x2, y2 = bbox
    cx = (x1 + x2) / 2 / max(frame_w, 1)
    cy = (y1 + y2) / 2 / max(frame_h, 1)
    return _brain_infer_zone(cx, cy)


def _format_multispeaker_transcript(
    named_pairs: "list[tuple[str | None, str]]",
) -> "tuple[str, str, list[str]]":
    """Phase 3B.4 — format a multi-speaker transcript for the brain.

    ``named_pairs`` is a list of ``(name_or_None, transcript)`` tuples in
    diarize order. ``name=None`` means the span didn't match the voice
    gallery — gets assigned ``unknown_1`` / ``unknown_2`` / ... in the
    order it appeared. Numbering is PER-UTTERANCE; no cross-turn state.

    Returns ``(brain_text, log_preview, labels)``:
      - ``brain_text``  — string injected into the user message.
          N=2 preserves legacy `[Name1]: text\\n[Name2]: text` format.
          N≥3 uses a `[N voices simultaneously]\\n{Name}: {text}\\n...`
          block — more readable with 3+ speakers than slash/newline
          mixing, and the header names exact count so brain sees the
          multi-speaker signal prominently.
      - ``log_preview`` — single-line slash-separated for ``[STT]`` log.
      - ``labels``      — list of resolved names (including ``unknown_N``)
          in order. Drives the voice_state "multi_speaker_speakers"
          field that downstream observability reads.

    Returns ``("", "", [])`` if fewer than 2 surviving transcripts —
    caller should treat single-speaker as the normal path.
    """
    if len(named_pairs) < 2:
        return "", "", []
    labels: list[str] = []
    unknown_i = 0
    for name, _ in named_pairs:
        if not name or name == "unknown":
            unknown_i += 1
            labels.append(f"unknown_{unknown_i}")
        else:
            labels.append(name)
    texts = [t for _, t in named_pairs]
    n = len(named_pairs)
    preview = " / ".join(
        f"{name}: \"{t[:60]}\"" for name, t in zip(labels, texts)
    )
    if n == 2:
        brain_text = "\n".join(
            f"[{name}]: {t}" for name, t in zip(labels, texts)
        )
    else:
        brain_text = (
            f"[{n} voices simultaneously]\n"
            + "\n".join(f"{name}: {t}" for name, t in zip(labels, texts))
        )
    return brain_text, preview, labels


def _count_scene_candidates(
    persons_in_frame: dict,
    unrecognized_tracks: dict,
    now: float,
    exclude: str | None = None,
) -> int:
    """Count how many distinct people are plausibly in the scene (excluding `exclude`)."""
    known = sum(
        1 for pid, info in persons_in_frame.items()
        if pid != exclude and now - info.get("last_recognized_at", 0) < VOICE_ROUTING_FACE_STALE_SECS
    )
    unrec = sum(
        1 for ts in unrecognized_tracks.values()
        if now - ts < VOICE_ROUTING_FACE_STALE_SECS
    )
    return known + unrec


def _set_state(new_state: PipelineState, person_name: str = None):
    _cur = _wiring._pipeline_state_store.peek_pipeline_state()
    if new_state == _cur:
        return
    print(f"[Pipeline] State: {_cur.name if _cur is not None else 'None'} -> {new_state.name}")
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_wiring._pipeline_state_store.set_pipeline_state(new_state))
    except RuntimeError:
        pass  # OPTIONAL: no running loop in sync test contexts
    mode_map = {
        PipelineState.WATCHING:    "watching",
        PipelineState.LISTENING:   "listening",
        PipelineState.THINKING:    "thinking",
        PipelineState.SPEAKING:    "speaking",
        PipelineState.ENROLLING:   "enrolling",
    }
    state.write(mode=mode_map[new_state], current_person=person_name)

def _scene_fingerprint(
    speaker_id: "str | None",
    now: float,
    active_sessions: "tuple",
    persons_in_frame: dict,
    unrecognized_tracks: dict,
    best_friend_id: "str | None",
    recent_visitors: "list[dict] | None",
) -> tuple:
    """Hashable key summarising all inputs that affect _build_scene_block output."""
    now_sec = int(now)  # 1-second granularity — output is stable within a second
    _snap_by_pid = {s.person_id: s for s in active_sessions}

    vis_items = []
    for pid, info in persons_in_frame.items():
        if now - info.get("last_seen", 0) >= SCENE_STALE_SECS:
            continue
        name = info.get("name", pid)
        _snap = _snap_by_pid.get(pid)
        person_type = _snap.person_type if _snap is not None else "known"
        if _is_disputed(pid):
            role = "disputed"
        elif pid == best_friend_id:
            role = "best_friend"
        elif person_type == "stranger":
            role = "visitor"
        else:
            role = "known"
        secs_ago = int(now - info.get("last_seen", now))
        vis_items.append((pid, name, role, pid == speaker_id, secs_ago))

    unrec_count = sum(
        1 for t in unrecognized_tracks.values()
        if now - t.get("last_seen", 0) < SCENE_STALE_SECS
    )

    if recent_visitors is None:
        rv_key: "frozenset | None" = None
    else:
        rv_key = frozenset(
            (v.get("person_id", ""), v.get("visitor_name", ""), str(v.get("safety_flags", [])))
            for v in recent_visitors
        )

    return (speaker_id, now_sec, frozenset(vis_items), unrec_count, best_friend_id, rv_key)

async def _get_scene_block_cached(
    speaker_id: "str | None",
    now: float,
    active_sessions: "tuple",
    persons_in_frame: dict,
    unrecognized_tracks: dict,
    best_friend_id: "str | None",
    recent_visitors: "list[dict] | None" = None,
) -> str:
    """Cache-backed wrapper for _build_scene_block (Wave 6 Item 23)."""
    if not SCENE_BLOCK_CACHE_ENABLED:
        return _build_scene_block(
            speaker_id, now, active_sessions, persons_in_frame,
            unrecognized_tracks, best_friend_id, recent_visitors,
        )

    key = _scene_fingerprint(
        speaker_id, now, active_sessions, persons_in_frame,
        unrecognized_tracks, best_friend_id, recent_visitors,
    )

    cached = _scene_block_store.peek(key, default=CACHE_MISS)
    if cached is not CACHE_MISS:
        return cached

    result = _build_scene_block(
        speaker_id, now, active_sessions, persons_in_frame,
        unrecognized_tracks, best_friend_id, recent_visitors,
    )
    await _scene_block_store.set(key, result)
    return result

def get_scene_block_cache_stats() -> dict:
    """Hit/miss/size stats for the scene_block cache."""
    return _scene_block_store.peek_stats()

def _build_scene_block(
    speaker_id: str | None,
    now: float,
    active_sessions: "tuple",
    persons_in_frame: dict,
    unrecognized_tracks: dict,
    best_friend_id: str | None,
    recent_visitors: "list[dict] | None" = None,
) -> str:
    """Always-on scene snapshot injected into the system prompt every turn.

    Session 108 Phase 3A.7 — restructured into 4 sections (Here now /
    Offscreen voice / Recent visitors / Safety concerns). Reviewer's
    lean-approach recommendation over LLM synthesis: structured
    descriptive block gets 80% of the value at 0% of the latency/cost,
    with proactive safety-flag surfacing baked in (Session 105 Bug N
    Part 3's per-visitor safety_flags metadata is now consumed here,
    not just in VISITOR CONTEXT).

    Sections render conditionally — each is omitted when empty so the
    block stays terse on single-person scenes. Safety concerns always
    render last so the brain reads them after the factual context.

    ``recent_visitors`` is pre-fetched by the caller from
    ``_brain_orchestrator.brain_db.get_recent_visitor_alerts(bf_id)``
    and filtered to nudges generated within SCENE_VISITOR_RECENCY_SECS.
    When None (caller unable to reach the orchestrator), those sections
    simply don't render — fallback-safe.
    """
    # ── Section 1: Who's here now (camera) ──────────────────────────
    _snap_by_pid_scene = {s.person_id: s for s in active_sessions}
    visible_lines: list[str] = []
    for pid, info in persons_in_frame.items():
        if now - info.get("last_seen", 0) >= SCENE_STALE_SECS:
            continue
        name = info.get("name", pid)
        _sc_snap = _snap_by_pid_scene.get(pid)
        person_type = _sc_snap.person_type if _sc_snap is not None else "known"
        # Finding M — disputed sessions take precedence over the sensor-matched
        # role so the SCENE block agrees with the IDENTITY DISPUTED block instead
        # of saying "best friend is present" for a contested identity.
        if _is_disputed(pid):
            role = "disputed identity"
        elif pid == best_friend_id:
            role = "best friend"
        elif person_type == "stranger":
            role = "visitor"
        else:
            role = "known"
        if pid == speaker_id:
            status = "speaking now"
        else:
            secs_ago = int(now - info.get("last_seen", now))
            status = "silent" if secs_ago < 2 else f"silent, last seen {secs_ago}s ago"
        visible_lines.append(f"- {name} ({role}) — {status}")

    unrec_count = sum(
        1 for ts in unrecognized_tracks.values()
        if now - ts < SCENE_STALE_SECS
    )
    if unrec_count:
        plural = "s" if unrec_count != 1 else ""
        visible_lines.append(f"- {unrec_count} unrecognized face{plural} (not greeted yet)")

    # ── Section 2: Offscreen voice ──────────────────────────────────
    offscreen_lines: list[str] = []
    for _off_snap in active_sessions:
        pid = _off_snap.person_id
        if pid in persons_in_frame:
            continue
        if _off_snap.session_type != "voice":
            continue
        last_spoke = _off_snap.last_spoke_at
        if now - last_spoke >= SCENE_VOICE_STALE:
            continue
        name = _off_snap.person_name
        person_type = _off_snap.person_type
        if pid == best_friend_id:
            role = "best friend"
        elif person_type == "stranger":
            role = "visitor"
        else:
            role = "known"
        secs_ago = int(now - last_spoke)
        status = "speaking now" if pid == speaker_id else f"heard {secs_ago}s ago"
        offscreen_lines.append(f"- {name} ({role}) — {status}")

    # ── Session 108 Phase 3A.7: Sections 3 & 4 — recent visitors + safety ──
    # `recent_visitors` is a list of nudge dicts (from
    # get_recent_visitor_alerts). Each has 'metadata' (visitor_name,
    # visitor_type, turn_count, safety_flags) + 'generated_at'. We
    # render two sections: human-readable visitor lines (Section 3)
    # AND an explicit Safety concerns rollup (Section 4) so the brain
    # can't miss them even if it skims.
    recent_visitor_lines: list[str] = []
    safety_concern_lines: list[str] = []
    if recent_visitors:
        for v in recent_visitors:
            if not isinstance(v, dict):
                continue
            gen_at = v.get("generated_at") or 0
            if gen_at and now - gen_at >= SCENE_VISITOR_RECENCY_SECS:
                continue
            meta = v.get("metadata") or {}
            vname  = meta.get("visitor_name") or "an unidentified visitor"
            vid    = meta.get("visitor_id")
            vturns = meta.get("turn_count") or 0
            vtype  = meta.get("visitor_type") or "stranger"
            # Don't surface the owner as their own visitor (defensive —
            # self-skip is enforced in get_recent_visitor_alerts too).
            if vid and vid == best_friend_id:
                continue
            mins_ago = int((now - gen_at) / 60) if gen_at else 0
            when = (
                "just now" if mins_ago < 1
                else f"{mins_ago} min ago"
            )
            role_label = "promoted visitor" if vtype == "known" else "visitor"
            turn_desc = "briefly" if vturns <= 2 else "for a while"
            recent_visitor_lines.append(
                f"- {vname} ({role_label}) visited {when} — spoke {turn_desc} ({vturns} turn(s))"
            )
            flags = meta.get("safety_flags") or []
            for flag in flags:
                # human-readable: expressed_suicidal_thoughts →
                # "expressed suicidal thoughts".
                human_flag = str(flag).replace("_", " ")
                safety_concern_lines.append(
                    f"- {vname}: {human_flag}"
                )

    # ── Assemble ────────────────────────────────────────────────────
    parts = ["<<<SCENE (internal — speak the meaning, never quote these tags)>>>"]
    if visible_lines:
        parts.append("Here now (camera):")
        parts.extend(visible_lines)
    else:
        parts.append("Nobody visible on camera.")
    if offscreen_lines:
        parts.append("Offscreen voice:")
        parts.extend(offscreen_lines)
    if recent_visitor_lines:
        parts.append("Recent visitors:")
        parts.extend(recent_visitor_lines)
    if safety_concern_lines:
        parts.append("Safety concerns (raised during recent visits):")
        parts.extend(safety_concern_lines)
    parts.append("<<<END SCENE>>>")
    return "\n".join(parts)
