"""core/room_orchestrator.py — P0.S7.D-D Stage 1 class extraction.

Consolidates 7 module-level room helpers from `pipeline.py` (~580 LOC) into
a `RoomOrchestrator` class that composes over the 6 existing state objects:
`SessionStore` (P0.7), `PipelineStateStore` (P0.6.6), `FaceDB`, the
`BrainOrchestrator`, `ConversationStore` (P0.6.3), and the
`_emotion_agents` dict.

**Stage 1 of two-stage extraction.** Stage 1 ships the class + module-level
shim functions in `pipeline.py` that defer dispatch to `RoomOrchestrator`
instance methods. 130 existing test sites keep working unchanged through
the shim layer. Stage 2 (post-bundled-canary follow-up) hard-deletes the
shims + migrates the 130 test sites; same trigger as P0.S7.D-C Stage 2
(combined PR candidate).

**3-layer defensive None-handling** (Plan v2 §4 refined):

- **Layer 1 — `pipeline._init_room_orchestrator()`** asserts all 6
  dependencies non-None at production boot.
- **Layer 2 — pipeline shim functions** raise ``RuntimeError`` if
  ``_room_orchestrator is None`` (fires in production AND tests).
- **Layer 3 — RoomOrchestrator methods** check only the deps each method
  actually needs (Plan v2 §4.3 dep-audit): the 4 pure-on-args methods
  don't check; the 2 brain_orchestrator-using methods degrade
  gracefully when the dep is None; `build_shared_context_block` takes
  `db` as an explicit arg (already a required parameter, so the
  caller's contract enforces non-None).

`RoomOrchestrator.__init__` STORES deps without asserting — tolerates
``None`` at construction time so the conftest autouse fixture can re-init
the class with whatever subset of deps the test context provides.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import time
import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.session_state import SessionStore, SessionSnapshot
    from core.pipeline_state_store import PipelineStateStore
    from core.conversation_store import ConversationStore
    from core.db import FaceDB
    from core.brain_agent import BrainOrchestrator

# NOTE: don't bind config flags at import time — tests patch the names on
# the `pipeline` module (`patch.object(pipeline, "SHARED_CONTEXT_BLOCK_ENABLED", False)`)
# expecting the read to see the patch. Each method reads flags via
# `pipeline.<FLAG>` lazy lookup so the patch propagates to the class
# methods unchanged. Same pattern as the late `import pipeline as _pl`
# already used for `_primary_person_id` + `_is_disputed`.


class RoomOrchestrator:
    """Composes 7 room-state helpers into a single class.

    Method names drop the legacy `_` prefix (D4) — public class API:
    `compute_room_audience`, `kairos_preferred_speaker`,
    `build_cross_person_excerpts`, `build_shared_context_block`,
    `build_room_block`, `fetch_recent_room_context`, `on_room_end`.

    Module-level shim functions in `pipeline.py` preserve the legacy
    names for the 130 existing test sites (Stage 1).
    """

    def __init__(
        self,
        session_store: "SessionStore | None" = None,
        pipeline_state_store: "PipelineStateStore | None" = None,
        face_db: "FaceDB | None" = None,
        brain_orchestrator: "BrainOrchestrator | None" = None,
        conversation_store: "ConversationStore | None" = None,
        emotion_agents: "dict | None" = None,
    ) -> None:
        # Plan v2 §4.1 refined — __init__ stores deps without asserting.
        # Production assertion lives in `_init_room_orchestrator()` (Layer 1).
        # Per-method Layer 3 checks fire only when a method needs a None dep.
        self._session_store         = session_store
        self._pipeline_state_store  = pipeline_state_store
        self._face_db               = face_db
        self._brain_orchestrator    = brain_orchestrator
        self._conversation_store    = conversation_store
        self._emotion_agents        = emotion_agents if emotion_agents is not None else {}

    # ── Method 1: compute_room_audience (pure on args) ──────────────────

    def compute_room_audience(
        self,
        participants: "set[str] | list[str] | tuple[str, ...]",
        person_id: str,
    ) -> "list[str]":
        """P0.S7 T-B + MEDIUM 4 — compute the ``audience_ids`` list for a
        ``log_turn`` call.

        Invariant: the speaker (``person_id``) is ALWAYS present in the
        returned audience list. Three cases:
          (a) participants empty → ``[person_id]``
          (b) participants non-empty AND person_id present → ``sorted(participants)``
          (c) participants non-empty AND person_id absent → ``sorted(participants ∪ {person_id})``
        """
        if not participants:
            return [person_id]
        audience_set: "set[str]" = set(participants)
        if person_id not in audience_set:
            audience_set.add(person_id)
        return sorted(audience_set)

    # ── Method 2: kairos_preferred_speaker (uses session_store) ─────────

    def kairos_preferred_speaker(self, best_friend_id: "str | None") -> "str | None":
        """Session 112 Part 2 — room-aware KAIROS speaker selection.

        Policy (gated by KAIROS_PREFER_BEST_FRIEND):
          1. Single-session room → return the one active pid.
          2. Multi-session room WITH best_friend active → prefer best_friend.
          3. Multi-session room WITHOUT best_friend → pick longest-silence pid.
        """
        if self._session_store is None:
            return None
        _snaps_ks = self._session_store.peek_all_snapshots()
        if not _snaps_ks:
            return None
        if len(_snaps_ks) == 1:
            return _snaps_ks[0].person_id
        # Late import — reads pipeline.KAIROS_PREFER_BEST_FRIEND so tests
        # that patch the flag on the pipeline module see the patch.
        import pipeline as _pl
        if not _pl.KAIROS_PREFER_BEST_FRIEND:
            return _pl._primary_person_id()
        if best_friend_id and any(s.person_id == best_friend_id for s in _snaps_ks):
            return best_friend_id
        now_ks = time.time()
        return max(
            _snaps_ks,
            key=lambda s: (
                now_ks - s.last_spoke_at,
                s.person_id,
            ),
        ).person_id

    # ── Method 3: build_cross_person_excerpts (D-C flag-gated; pure on args) ─

    def build_cross_person_excerpts(
        self,
        speaker_id: str,
        active_sessions: "tuple",
        conversation: dict,
        best_friend_id: "str | None",
    ) -> "str | None":
        """Build a room-state context block when multiple people are active.

        P0.S7.D-C Stage 1 — flag-gated behind ``CROSS_PERSON_EXCERPTS_ENABLED``.
        D-C Phase 3 test 10 verifies the guard survives the D-D move.
        Stage 2 of D-C hard-deletes; same canary trigger as Stage 2 of D-D.
        """
        # P0.S7.D-C flag-gate preservation — Phase 3 test 10 inverse-check
        # asserts this guard remains in the moved method body.
        from core import config as _config
        if not _config.CROSS_PERSON_EXCERPTS_ENABLED:
            return None
        if len(active_sessions) <= 1:
            return None

        # Late imports so the class file stays light at import time.
        import pipeline as _pl

        present_parts = []
        for _cx_snap in active_sessions:
            pid = _cx_snap.person_id
            name = _cx_snap.person_name
            if _pl._is_disputed(pid):
                role = "disputed identity"
            elif pid == best_friend_id:
                role = "best friend"
            elif _cx_snap.person_type == "stranger":
                role = "visitor"
            else:
                role = "known person"
            tag = " — speaking now" if pid == speaker_id else ""
            present_parts.append(f"{name} ({role}{tag})")

        now_ts = time.time()
        cross_lines: list[str] = []
        for _cx_snap2 in active_sessions:
            pid = _cx_snap2.person_id
            if pid == speaker_id:
                continue
            other_name = _cx_snap2.person_name
            other_started = float(_cx_snap2.started_at)
            other_hist    = conversation.get(pid, [])
            in_session = [
                msg for msg in other_hist
                if float(msg.get("ts") or 0.0) >= other_started
            ]
            recent = in_session[-6:] if len(in_session) > 6 else in_session
            for msg in recent:
                ts = float(msg.get("ts") or 0.0)
                age_secs = max(0.0, now_ts - ts) if ts else 0.0
                if not ts:
                    age_label = ""
                elif age_secs < 60:
                    age_label = "just now"
                else:
                    age_label = f"{int(age_secs / 60)}m ago"
                age_suffix = f" ({age_label})" if age_label else ""
                if msg.get("role") == "user":
                    role_label = other_name
                else:
                    addressed = msg.get("addressed_to")
                    role_label = (
                        f"you [to {addressed}]"
                        if addressed
                        else "you"
                    )
                content = (msg.get("content") or "")[:120]
                cross_lines.append(f"  {role_label}{age_suffix}: {content}")

        lines = ["People in room: " + ", ".join(present_parts)]
        if cross_lines:
            lines.append("Recent context from others in the room:")
            lines.extend(cross_lines)

        return (
            "<<<ROOM STATE (internal — never quote these markers, treat as natural awareness)>>>\n"
            + "\n".join(lines)
            + "\n<<<END ROOM STATE>>>"
        )

    # ── Method 4: build_shared_context_block (D-A; db arg threaded) ─────

    def build_shared_context_block(
        self,
        room_session_id: "str | None",
        requester_pid: str,
        best_friend_id: "str | None",
        db: "FaceDB",
        is_disputed_fn,
        active_session_count: int,
        limit: int = 10,
        now: "float | None" = None,
    ) -> "str | None":
        """Phase 3B D-A — render `<<<SHARED CONTEXT>>>` block.

        P0.S7.1 observability counter `_last_shared_context_row_count` is
        kept in sync on the `pipeline` module via late import — preserves
        the existing observability contract (caller at conversation_turn
        line ~5454 reads `pipeline._last_shared_context_row_count` for the
        `[Brain] Context:` summary line).
        """
        # Late import to write the module-level observability counter
        # AND read the gating flag (so tests that patch
        # pipeline.SHARED_CONTEXT_BLOCK_ENABLED see the patch).
        import pipeline as _pl

        # Layer 3 None-handling (Pre-P1 Bundle 3 §3 D3 BUG-9 hybrid disposition):
        # test fixtures may pass `db=None` per the conftest autouse pattern.
        # Degrade gracefully; production callers route through `_init_room_orchestrator`
        # which raises RuntimeError if `_face_db_ref` is None.
        if db is None:
            _pl._last_shared_context_row_count = 0
            print("[SharedContext] gate=db_none → skip (test-context None tolerance)")
            return None

        # 1. flag gate.
        if not _pl.SHARED_CONTEXT_BLOCK_ENABLED:
            _pl._last_shared_context_row_count = 0
            print("[SharedContext] gate=flag_off → skip")
            return None
        # 2. T-A — disputed-caller skip. MUST run BEFORE any DB read
        # per Plan v2 §6 gate-order; Phase 3 test asserts via AST walk.
        # Moved BEFORE the multi-person + room_session_id gates so the
        # D2 fallback branch (single-person scenes) is ALSO disputed-
        # skipped uniformly.
        if is_disputed_fn(requester_pid):
            _pl._last_shared_context_row_count = 0
            print(f"[SharedContext] gate=disputed (requester='{requester_pid}') → skip")
            return None

        # Fast path — multi-person scene with current room_session_id.
        rows: "list[dict]" = []
        if active_session_count >= 2 and room_session_id:
            rows = db.get_recent_room_conversation(
                room_session_id=room_session_id,
                requester_pid=requester_pid,
                best_friend_id=best_friend_id,
                limit=limit,
            )
            if not rows:
                _pl._last_shared_context_row_count = 0
                print(f"[SharedContext] room={room_session_id} requester={requester_pid} rows=0 → skip")
                return None
            print(f"[SharedContext] room={room_session_id} requester={requester_pid} rows={len(rows)} → rendered (fast path)")
        else:
            # P0.S7.5 D2 — fallback widening. Current scene is single-
            # person OR has no room_session_id, but the requester may
            # have participated in recent multi-person rooms whose
            # persisted history is what the owner is asking about
            # (canary 2026-05-19 root cause #2). Look up recent
            # audience rooms; merge their histories chronologically.
            from core.config import SHARED_CONTEXT_RECENT_AUDIENCE_HOURS
            recent_room_ids = db.get_recent_audience_rooms(
                requester_pid=requester_pid,
                best_friend_id=best_friend_id,
                hours_back=SHARED_CONTEXT_RECENT_AUDIENCE_HOURS,
                limit=5,
            )
            if not recent_room_ids:
                _pl._last_shared_context_row_count = 0
                print(
                    f"[SharedContext] gate=single_person + no_recent_audience "
                    f"(count={active_session_count}) → skip"
                )
                return None
            for _rid in recent_room_ids:
                _room_rows = db.get_recent_room_conversation(
                    room_session_id=_rid,
                    requester_pid=requester_pid,
                    best_friend_id=best_friend_id,
                    limit=limit,
                )
                rows.extend(_room_rows)
            if not rows:
                _pl._last_shared_context_row_count = 0
                print(
                    f"[SharedContext] gate=recent_audience_empty "
                    f"(rooms={len(recent_room_ids)}) → skip"
                )
                return None
            # Merge ordering — sort chronologically + cap at limit.
            rows.sort(key=lambda r: r.get("ts") or 0.0)
            if len(rows) > limit:
                rows = rows[-limit:]
            print(
                f"[SharedContext] gate=recent_audience "
                f"(rooms={len(recent_room_ids)}, rows={len(rows)}) → rendered (D2 widening)"
            )

        _pl._last_shared_context_row_count = len(rows)

        now_ts = now if now is not None else time.time()
        name_cache: "dict[str, str]" = {}

        def _name_for(pid: str) -> str:
            if pid in name_cache:
                return name_cache[pid]
            person = db.get_person(pid)
            nm = (person or {}).get("name") or pid
            name_cache[pid] = nm
            return nm

        out_lines: list[str] = []
        for r in rows:
            pid = r.get("person_id") or ""
            role = r.get("role") or ""
            text = (r.get("text") or "")[:120]
            ts = float(r.get("ts") or 0.0)
            addressed_to = r.get("addressed_to")

            age_secs = max(0.0, now_ts - ts) if ts else 0.0
            if not ts:
                age_label = ""
            elif age_secs < 60:
                age_label = "just now"
            else:
                age_label = f"{int(age_secs / 60)}m ago"
            age_suffix = f" ({age_label})" if age_label else ""

            if role == "user":
                role_label = _name_for(pid)
            else:
                role_label = (
                    f"you [to {addressed_to}]"
                    if addressed_to
                    else "you"
                )
            out_lines.append(f"  {role_label}{age_suffix}: {text}")

        return (
            "<<<SHARED CONTEXT (room conversation log — persisted history)>>>\n"
            "Recent room-scoped turns from your conversation log:\n"
            + "\n".join(out_lines)
            + "\n<<<END SHARED CONTEXT>>>"
        )

    # ── Method 5: build_room_block (S113 P3B.1; pure on args + emotion_agents) ─

    def build_room_block(
        self,
        active_sessions: "tuple",
        conversation: dict,
        emotion_agents: dict,
        room_start_ts: "float | None",
        turn_cap: int = 10,
        now: "float | None" = None,
        best_friend_id: "str | None" = None,
    ) -> "str | None":
        """Phase 3B.1 — unified multi-person room-state block.

        P0.S7.D-C D3 — Section 1 role hierarchy mirrors SCENE + legacy:
        `_is_disputed → best_friend_id → person_type`.
        """
        # Late import — reads core.config.ROOM_BLOCK_ENABLED so tests that
        # patch via `monkeypatch.setattr(core.config, "ROOM_BLOCK_ENABLED",
        # False)` see the patch. Matches the legacy pattern.
        from core.config import ROOM_BLOCK_ENABLED as _RB_ENABLED
        if not _RB_ENABLED:
            return None
        if len(active_sessions) < 2:
            return None
        if now is None:
            now = time.time()
        # Pipeline reference for _is_disputed (also tracks reassignments).
        import pipeline as _pl

        # ── Section 1: active speakers list ─────────────────────────────
        _active_lines: list[str] = []
        for _rs in active_sessions:
            pid = _rs.person_id
            if _pl._is_disputed(pid):
                role = "disputed identity"
            elif pid == best_friend_id:
                role = "best_friend"
            else:
                role = _rs.person_type
            _active_lines.append(f"{_rs.person_name} ({role})")
        _active_str = ", ".join(_active_lines)

        # ── Section 2: room duration (optional) ─────────────────────────
        _duration_line = ""
        if room_start_ts is not None:
            _elapsed_secs = max(0.0, now - room_start_ts)
            if _elapsed_secs < 60:
                _dur_phrase = "just started"
            elif _elapsed_secs < 3600:
                _dur_phrase = f"started {int(_elapsed_secs / 60)} min ago"
            else:
                _hrs = int(_elapsed_secs / 3600)
                _dur_phrase = f"started {_hrs} hr ago" if _hrs == 1 else f"started {_hrs} hrs ago"
            _duration_line = f"Room session {_dur_phrase}."

        # ── Section 3: interleaved recent turns ─────────────────────────
        _boundary = room_start_ts if room_start_ts is not None else 0.0
        _all_msgs: list[tuple[float, str, dict]] = []
        for _rs in active_sessions:
            _pname = _rs.person_name
            _history = conversation.get(_rs.person_id, []) or []
            for _msg in _history:
                _ts = _msg.get("ts", 0.0)
                if _ts < _boundary:
                    continue
                _all_msgs.append((_ts, _pname, _msg))
        _all_msgs.sort(key=lambda x: x[0])
        if len(_all_msgs) > turn_cap:
            _all_msgs = _all_msgs[-turn_cap:]

        def _age_label(ts: float) -> str:
            _delta = max(0.0, now - ts)
            if _delta < 60:
                return "just now"
            if _delta < 3600:
                return f"{int(_delta / 60)}m ago"
            return f"{int(_delta / 3600)}h ago"

        _turn_lines: list[str] = []
        for _ts, _pname, _msg in _all_msgs:
            _role     = _msg.get("role", "user")
            _content  = (_msg.get("content") or "").strip()
            if not _content:
                continue
            _age      = _age_label(_ts)
            _addr     = _msg.get("addressed_to")
            if _role == "assistant":
                # Assistant: "Kara" (the system) → addressee
                _speaker = "Kara"
                if _addr:
                    _turn_lines.append(f"  [{_age}] {_speaker} \u2192 {_addr}: \"{_content}\"")
                else:
                    _turn_lines.append(f"  [{_age}] {_speaker}: \"{_content}\"")
            else:
                # User turn — speaker is the session's person_name.
                _turn_lines.append(f"  [{_age}] {_pname}: \"{_content}\"")

        # ── Section 4: per-person mood ──────────────────────────────────
        _mood_lines: list[str] = []
        for _rs in active_sessions:
            _ag = emotion_agents.get(_rs.person_id) if emotion_agents else None
            if _ag is None:
                _mood = "unknown"
            else:
                try:
                    _label, _score = _ag.get_dominant_emotion()
                    _mood = _label if _label else "neutral"
                except Exception:
                    _mood = "neutral"
            _mood_lines.append(f"  {_rs.person_name}: {_mood}")

        # Assemble — verbatim match to legacy pipeline._build_room_block.
        _parts: list[str] = ["<<<ROOM>>>"]
        _parts.append(f"Active in this room: {_active_str}")
        if _duration_line:
            _parts.append(_duration_line)
        if _turn_lines:
            _parts.append("")
            _parts.append("Recent turns (oldest first, most recent last):")
            _parts.extend(_turn_lines)
        _parts.append("")
        _parts.append("Current emotional state:")
        _parts.extend(_mood_lines)
        _parts.append("<<<END ROOM>>>")

        # Phase 3B.3 — TURN ARBITRATION rules. Verbatim match to legacy.
        from core.config import TURN_ARBITRATION_ENABLED
        if TURN_ARBITRATION_ENABLED:
            _parts.append("")
            _parts.append("<<<TURN ARBITRATION>>>")
            _parts.append(
                "Default: respond to the current speaker (the one whose turn is being processed).\n"
                "No [addressing:X] marker needed.\n"
                "\n"
                "Emit [addressing:<name>] marker ONLY when one of these applies:\n"
                "\n"
                "1. MUMBLE CONTINUATION. Another speaker just gave a brief affirmation like\n"
                "   \"yeah\", \"uh-huh\", \"okay\", \"right\" \u2014 NOT a new turn demanding response.\n"
                "   Continue the thread with the PRIOR substantive speaker, not the mumbler.\n"
                "   Example: Jagan asks weather \u2192 Kara answers \u2192 Lexi: \"uh-huh\" \u2192 Kara should\n"
                "   continue with Jagan (not redirect to Lexi).\n"
                "\n"
                "2. PENDING THREAD CIRCLE-BACK. You helped speaker A earlier, the answer was\n"
                "   incomplete or promised follow-up, and speaker B took over the conversation.\n"
                "   After B's thread resolves naturally, you may circle back:\n"
                "   \"By the way, [addressing:A], about your earlier question...\"\n"
                "   ONLY do this when the current moment naturally allows it. Don't force.\n"
                "\n"
                "3. LONG-SILENCE RE-ENGAGEMENT. If a speaker (especially best_friend) has been\n"
                "   silent for 4+ turns while others dominated, a gentle check-in is fine.\n"
                "   \"[addressing:<quiet_speaker>], you've been quiet \u2014 what do you think?\"\n"
                "   ONLY if context naturally allows. Don't interrupt active thread.\n"
                "\n"
                "4. DIRECT QUESTION ACROSS CONTEXT. Speaker A asked a clear question to you\n"
                "   just now, but speaker B spoke last (even briefly). The question is still\n"
                "   unanswered. Emit [addressing:A] and respond to the question.\n"
                "\n"
                "DO NOT emit marker if:\n"
                "- None of the above apply\n"
                "- You're uncertain \u2014 default to current speaker is safer\n"
                "- The current speaker has clearly directed the conversation\n"
                "\n"
                "Marker format: `[addressing:Jagan]` on its own line at the START of your response.\n"
                "The marker will be stripped before TTS \u2014 the user won't hear it, only the\n"
                "pipeline uses it for attribution."
            )
            _parts.append("<<<END TURN ARBITRATION>>>")

        return "\n".join(_parts)

    # ── Method 6: fetch_recent_room_context (brain_orchestrator) ────────

    def fetch_recent_room_context(self, person_id: "str | None") -> "dict | None":
        """Phase 3B.6 — fetch the most recent room_summaries row.

        Layer 3 None check (Plan v2 §4.3): degrades gracefully when
        ``self._brain_orchestrator`` is None. Also reads the live
        ``pipeline._brain_orchestrator`` via late import so tests that
        reassign the module attribute see the updated reference (matches
        the legacy module-level helper's lazy-lookup semantic).
        """
        from core.config import (
            ROOM_END_SYNTHESIS_ENABLED as _ENABLED,
            ROOM_RECENT_CONTEXT_HOURS as _HOURS,
        )
        if not _ENABLED or not person_id:
            return None
        import pipeline as _pl
        _bo = _pl._brain_orchestrator if _pl._brain_orchestrator is not None else self._brain_orchestrator
        if _bo is None:
            return None
        try:
            return _bo.brain_db.get_recent_room_context(
                person_id, hours=_HOURS,
            )
        except Exception as _ex:
            print(f"[Pipeline] recent-room-context fetch failed: {_ex!r}")
            return None

    # ── Method 7: on_room_end (async; brain_orchestrator) ───────────────

    async def on_room_end(
        self,
        room_session_id: str,
        speaker_pids: "list[str] | None" = None,
        started_at: "float | None" = None,
    ) -> None:
        """Session 112 Part 1 — hook fired when the last person leaves.

        Layer 3 None check (Plan v2 §4.3): degrades gracefully when
        ``self._brain_orchestrator`` is None.
        """
        _participant_count = len(speaker_pids or [])
        _age_str = ""
        if started_at:
            _age_secs = max(0.0, time.time() - started_at)
            _age_str = f", duration={int(_age_secs)}s"
        print(
            f"[Room] Room-end hook fired for {room_session_id} "
            f"(participants={_participant_count}{_age_str})"
        )
        # Late-lookup pipeline._brain_orchestrator so tests that reassign
        # the module attribute mid-run see the updated reference (legacy
        # module-level helper's lazy semantic).
        import pipeline as _pl
        _bo = _pl._brain_orchestrator if _pl._brain_orchestrator is not None else self._brain_orchestrator
        if (
            _bo is not None
            and speaker_pids is not None
            and len(speaker_pids) >= 2
        ):
            try:
                asyncio.create_task(
                    _bo.synthesize_room(
                        room_session_id=room_session_id,
                        speaker_pids=list(speaker_pids),
                        started_at=started_at,
                    )
                )
                print(
                    f"[Room] Synthesis dispatched (background) for "
                    f"{room_session_id} \u2014 speakers={list(speaker_pids)}"
                )
            except RuntimeError:
                print(
                    f"[Room] Synthesis skipped for {room_session_id} \u2014 "
                    f"no running loop"
                )
        elif _bo is None:
            print(f"[Room] Synthesis skipped for {room_session_id} \u2014 orchestrator unavailable")
        elif speaker_pids is None or len(speaker_pids) < 2:
            print(
                f"[Room] Synthesis skipped for {room_session_id} \u2014 "
                f"single-speaker (per-person session-end already handled it)"
            )
