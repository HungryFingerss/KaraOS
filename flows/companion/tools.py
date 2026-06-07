# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors
"""flows/companion/tools.py — the companion LLM-tool dispatch surface (P1.A1 SP-6.2).

The tool-dispatch entry point (_execute_tool) + the 5 identity/action handlers
(_handle_update_person_name / _handle_report_identity_mismatch /
_handle_update_system_name / _handle_shutdown / _handle_search_memory) + the
_ToolContext dataclass + the _TOOL_HANDLERS registry + the move-with helpers
(_tool_allowed / _is_enrollment_mishear_candidate / _log_intent_divergence /
_INVALID_SYSTEM_NAMES / _SHUTDOWN_QUESTION_RE), relocated VERBATIM from pipeline.py.
App layer: flows -> runtime -> core (imports runtime.{wiring,session,text,
identity_cache} + core.config; never pipeline). pipeline.py re-exports every
symbol so conversation_turn + the existing test suite stay byte-identical.
"""
from __future__ import annotations

import asyncio
import dataclasses
import re
import runtime.wiring as _wiring
import time
from core.config import (
    DISPUTE_RENAME_BLOCK_THRESHOLD, ENROLLMENT_RENAME_GRACE_SECS, ENROLLMENT_RENAME_MAX_TURNS, ENROLLMENT_RENAME_VOICE_THRESHOLD, IDENTITY_DENIAL_PATTERNS, PERSON_NAME_ASSIGN_PATTERNS, SYSTEM_NAME_ASSIGN_PATTERNS, TOOL_PRIVILEGES, TOOL_REPEAT_MAX_CONSECUTIVE, TOOL_TIMEOUT_OVERRIDES, TOOL_TIMEOUT_SECS,
)
from runtime.session import _is_disputed
from runtime.text import (
    _intent_allows, _nfkc_lower, _user_text_gate_passes, sanitize_name,
)
from runtime.wiring import _conversation_store, _presence_store
from runtime.identity_cache import _invalidate_bf_cache


# Per-tool silent fallback spoken when the LLM calls a tool with no text.
# Names that are clearly placeholder/invalid and should never be stored.
_INVALID_SYSTEM_NAMES = frozenset({"none", "unknown", "unnamed", "noname", "null", "undefined", "n_a", "na"})
# Detects questions ABOUT shutdown (not commands to shutdown).
# "why did you shut down?" or "when did you turn off?" → question, not command.
_SHUTDOWN_QUESTION_RE = re.compile(
    r'\b(?:why|how|when|what|did|do|does|was|were|would|could)\b.{0,40}'
    r'\b(?:shut\s*down|shutdown|turn\s*off|goodbye|sleep|stop)\b',
    re.IGNORECASE,
)
def _tool_allowed(tool_name: str, caller_type: str) -> bool:
    """Return True iff ``caller_type`` is permitted to invoke ``tool_name``.

    Fail-closed: tools NOT in ``TOOL_PRIVILEGES`` are BLOCKED (treated as
    always-disallowed). Missing-table entries are a configuration bug — the
    startup assertion in run() ensures every tool in brain.TOOLS has a row
    here, so this path fires only for genuinely unregistered callers.
    """
    allowed = TOOL_PRIVILEGES.get(tool_name)
    if allowed is None:
        return False  # unregistered tool → blocked (fail-closed)
    return caller_type in allowed
def _is_enrollment_mishear_candidate(
    db: "FaceDB | None",
    person_id: str,
    session,
) -> bool:
    """Session 100 Bug F — is this a fresh-enrollment session whose stored
    name has no voice corroboration yet, so a speaker-grounded rename should
    flow through the stranger-promotion chain instead of flipping to
    disputed?

    2026-04-23 canary scenario: STT heard "My name is Jagan" as "My name
    is Gevan" at first-boot enrollment. Jagan's corrective "No, my name
    is Jagan" landed on a best_friend session whose ONLY corroboration
    was the face match — voice profile was empty, session was seconds old.
    The classic dispute-flip ('known'/'best_friend' rename-on-session =
    suspicious sensor) was designed for mid-session impersonation attempts,
    not for enrollment-mishear correction. This helper distinguishes the
    two cases by checking:

      1. Session started within ENROLLMENT_RENAME_GRACE_SECS. A week-old
         session with mature voice history has had plenty of opportunity
         for the user to correct a wrong name — the grace window is
         short enough that 'I've been called Gevan for a month and now
         I'd like to switch to Jagan' does NOT qualify.
      2. DB voice embedding count < ENROLLMENT_RENAME_VOICE_THRESHOLD.
         Below this floor, the system has not yet accumulated enough
         voice data to independently corroborate the stored name — the
         face match is the only evidence, and face + self-assertion is
         sufficient grounds to rename.

    Caller must have ALREADY validated the rename claim against the
    classifier (assign_own_name intent, grounded in user_text) — this
    helper only makes the routing decision between dispute-flip and
    promotion-chain rename; it is not itself a security gate.
    """
    started_at = float(session.started_at if session is not None else 0.0)
    # Pre-P1 Bundle 5 fix — Bundle 3 mis-classified this reader as DEADLINE-MATH
    # and migrated it to monotonic, subtracting a wall-clock timestamp from a
    # monotonic clock so a stale session read as "fresh".
    # WALLCLOCK: session.started_at is stored as wall-clock at open_session
    # (_open_session sets now=time.time()); the age check must use the same clock.
    if started_at <= 0 or time.time() - started_at > ENROLLMENT_RENAME_GRACE_SECS:
        return False
    # Canary #3 (2026-05-30 Jagan→Lexi): B1 — an established multi-turn conversation is
    # PAST the enrollment moment. A genuine mishear-correction happens in the first few
    # turns while the name is fresh; by canary turn 55 the name had been used 50+ times
    # uncorrected. Turn-count is the principled "is this still enrollment?" signal —
    # vision is non-discriminative (both a genuine turn-1 mishear AND the canary had the
    # face on camera; the real speaker was voice-only / never on camera). Once Part A
    # fills the gallery, voice_n>=5 independently blocks this too — B1 covers the
    # pre-gallery window. Q4: turn-count alone, no vision signal.
    _user_turns = int(getattr(session, "user_turns", 0) or 0)
    if _user_turns > ENROLLMENT_RENAME_MAX_TURNS:
        return False
    if db is None:
        # No DB means we can't verify voice count — fail to the safer
        # dispute-flip path. In production the db arg is always set.
        return False
    try:
        voice_n = db.voice_embedding_count(person_id)
    except Exception as _e:
        # #123 D3: LOG the fail-closed decision. voice_embedding_count failed → fail closed
        # to the dispute path (return False). This guards BOTH the Jagan→Lexi mishear-rename
        # corruption AND a persistently-broken gate silently never working — the log surfaces
        # the latter, which a bare `return False` would hide.
        print(f"[Enroll] voice_embedding_count failed for {person_id!r}: {_e!r} "
              f"— failing closed to dispute path")
        return False
    return voice_n < ENROLLMENT_RENAME_VOICE_THRESHOLD
# P1.A1 SP-6.2: multi-context — called from the handlers in THIS module AND from
# conversation_turn (pipeline, via the re-export). A test asserting handler-side firing
# must patch flows.companion.tools._log_intent_divergence, NOT the pipeline re-export
# (the binding split is the finding-#1 / SP-6.1 lesson).
def _log_intent_divergence(
    *,
    tool_name:    str,
    sidecar:      "dict | None",
    gate_decision: str,
    user_text:    "str | None" = None,
    person_id:    "str | None" = None,
    turn_id:      "int | None" = None,
) -> None:
    """P1.7a helper — one row per gated-tool decision that routes through
    the intent gate. Wraps ``BrainDB.log_intent_divergence`` with safe
    access so unit tests (and the early-boot path before the orchestrator
    is up) don't need to stand up a full brain pipeline.

    Callers should pass the sidecar dict from ``_classify_intent`` (or
    ``None`` when the classifier wasn't consulted — shadow-mode disabled,
    timeout, parse failure); we unpack the structured_* columns from it.
    ``gate_decision`` is a short free-form string encoding what happened:
    ``'allow'`` / ``'reject: <reason>'`` / ``'regex_fallback_allow'`` /
    ``'regex_fallback_reject'`` / ``'both_unavailable_allow_with_warning'``.

    Any exception is swallowed with a warning log — the gate's primary job
    is dispatch, not bookkeeping, and a write failure must not block the
    user's turn."""
    orch = _wiring._brain_orchestrator
    if orch is None:
        # Early boot / test fixture — orchestrator not yet initialized. Not
        # an error; log debug and move on.
        return
    brain_db = getattr(orch, "_brain_db", None)
    if brain_db is None:
        return
    si  = sidecar.get("turn_intent") if sidecar else None
    sv  = sidecar.get("extracted_value") if sidecar else None
    sc  = sidecar.get("confidence") if sidecar else None
    try:
        brain_db.log_intent_divergence(
            tool_proposed         = tool_name,
            gate_decision         = gate_decision,
            user_text             = user_text,
            person_id             = person_id,
            turn_id               = turn_id,
            structured_intent     = si,
            structured_extracted  = sv,
            structured_confidence = float(sc) if sc is not None else None,
        )
    except Exception as e:
        print(f"[Intent] divergence log write failed: {type(e).__name__}: {e}")
@dataclasses.dataclass(frozen=True, slots=True)
class _ToolContext:
    """P0.8: context bundle passed to extracted tool handlers.

    Carries the per-call inputs and derived state computed by _execute_tool
    after the Layer 0 / repeat / privilege gates pass. Handlers reference
    ctx.<field> instead of local closures — required by the dispatch-table
    refactor that wraps each handler invocation in asyncio.wait_for.
    """
    args: dict
    person_id: str
    person_name: str
    db: "FaceDB"
    user_text: str
    intent_sidecar: "dict | None"
    exec_snap: "object | None"      # SessionSnapshot or None
    caller_type: str                # session person_type or "stranger" fallback
async def _handle_update_person_name(args: dict, ctx: "_ToolContext") -> "str | None":
    """P0.8 extracted handler — verbatim move of update_person_name branch from _execute_tool."""
    # P0.8 mechanical extraction (handler body is verbatim from the original
    # _execute_tool branch).  Local names rebind from ctx so the body reads
    # identically.  Intent + grounding gates stay inside — P1.A3 extracts
    # them next.
    args           = ctx.args
    person_id      = ctx.person_id
    person_name    = ctx.person_name
    db             = ctx.db
    user_text      = ctx.user_text
    intent_sidecar = ctx.intent_sidecar
    _exec_snap     = ctx.exec_snap

    new_name, _ = sanitize_name(args.get("name") or "")
    _sess_type  = _exec_snap.person_type if _exec_snap is not None else "known"

    # Session 101 Bug F.2 — enrollment-mishear escape hatch with
    # widened intent set. Runs BEFORE the normal `_intent_allows` gate
    # because natural correction phrasings ("No, it's not Javan, it's
    # Jagan") classify as `deny_identity` (linguistically correct —
    # denial + correction) rather than `assign_own_name`. The classic
    # `_intent_allows` check on `update_person_name` only accepts
    # `assign_own_name`, so the original Session 100 Bug F escape
    # hatch (which runs AFTER the gate) never activated for the exact
    # phrasing users actually produce. 2026-04-23 re-canary: rename
    # blocked → person_id stays at STT-mangled "Jawan" → all
    # downstream facts stored under wrong entity, PromptPrefAgent
    # encoded "use 'Jawan' as preferred form," dashboard frozen.
    #
    # Widening: during the fresh-enrollment window (face only, no
    # voice corroboration — same gate as Session 100's
    # _is_enrollment_mishear_candidate), accept 3 intents for
    # update_person_name: assign_own_name, deny_identity,
    # confirm_identity. Each MUST still satisfy the full grounding
    # contract (extracted_value present AND appears NFKC-casefolded
    # in user_text) so ungrounded hallucinations can't sneak through.
    # Mature-session security (mid-session rename → dispute) is
    # PRESERVED because `_is_enrollment_mishear_candidate` fails on
    # any session past the grace window or with voice samples.
    if (
        new_name
        and new_name.lower() != person_name.lower()
        and _sess_type in ("known", "best_friend")
        and _is_enrollment_mishear_candidate(db, person_id, _exec_snap)
        and intent_sidecar is not None
    ):
        from core.config import INTENT_CONFIDENCE_MIN as _ICM
        _mishear_intents = frozenset((
            "assign_own_name", "deny_identity", "confirm_identity",
        ))
        _mi_intent = intent_sidecar.get("turn_intent") or ""
        _mi_conf   = float(intent_sidecar.get("confidence") or 0.0)
        _mi_val    = intent_sidecar.get("extracted_value")
        _mi_val_s  = str(_mi_val).strip() if _mi_val else ""
        _grounded  = bool(_mi_val_s) and (
            _nfkc_lower(_mi_val_s) in _nfkc_lower(user_text or "")
        )
        if (
            _mi_intent in _mishear_intents
            and _mi_conf >= _ICM
            and _grounded
        ):
            if db:
                db.update_person_name(person_id, new_name)
                _invalidate_bf_cache()  # Session 115 Fix 2 — rename may target bf
            _old_pat_mh2 = re.compile(
                r'\b' + re.escape(person_name) + r'\b', re.IGNORECASE,
            )
            for _msg_mh in _conversation_store.peek_history(person_id):
                _msg_mh["content"] = _old_pat_mh2.sub(
                    new_name, _msg_mh["content"],
                )
            if _wiring._session_store.peek_snapshot(person_id) is not None:
                # P0.S7.5 D3 — await rename synchronously (was create_task);
                # downstream canonical-ack peek_snapshot observes new name.
                try:
                    await _wiring._session_store.rename(person_id, new_name)
                except Exception as _rn_e:
                    print(f"[Pipeline] _session_store.rename failed: {_rn_e!r}")  # OPTIONAL
            # Session 102 Bug F.3: update the in-frame cache
            # immediately so the SCENE block and [Vision] logs don't
            # keep rendering the old name until the next background
            # scan lands (~1s). Belt-and-braces with the background-
            # scan refresh.
            try:
                asyncio.get_running_loop().create_task(
                    _presence_store.update_name(person_id, new_name)
                )
            except RuntimeError:
                pass  # OPTIONAL: no running loop in test/early-boot context
            if _wiring._brain_orchestrator:
                _wiring._brain_orchestrator.on_identity_confirmed(
                    person_id, person_name, new_name,
                )
            print(
                f"[Pipeline] Enrollment-mishear rename (Bug F.2): "
                f"{person_name!r} → {new_name!r} "
                f"(intent={_mi_intent}, person_type={_sess_type!r}, "
                f"conf={_mi_conf:.2f})"
            )
            _log_intent_divergence(
                tool_name="update_person_name",
                sidecar=intent_sidecar,
                gate_decision=f"allow_mishear_{_mi_intent}",
                user_text=user_text, person_id=person_id,
            )
            return "handled"

    # VISION_ROADMAP P1.7a (Session 85): classifier-first gate, regex
    # fallback. Order: (1) if _classify_intent fired this turn, use
    # _intent_allows — dual-gate (intent match + confidence floor +
    # grounding + arg cross-check) is the new authority. (2) If classifier
    # was unavailable AND INTENT_FALLBACK_TO_REGEX=True, fall through to
    # the legacy regex gate (Session 73's capture-group rule). (3) If
    # classifier was unavailable AND fallback is disabled (P1.17+), allow
    # with a warning — silently dropping mutation tools on classifier
    # failure would be worse UX than a logged wide-open path. All three
    # outcomes land a row in brain.db.intent_divergences for Phase 5.
    if new_name:
        from core.config import INTENT_FALLBACK_TO_REGEX
        _gate_allowed = True
        _gate_reason  = "no gate evaluated"
        if intent_sidecar is not None:
            _allowed, _reason = _intent_allows(
                tool_name="update_person_name",
                turn_intent=intent_sidecar.get("turn_intent") or "",
                confidence=float(intent_sidecar.get("confidence") or 0.0),
                extracted_value=intent_sidecar.get("extracted_value"),
                user_text=user_text,
                tool_args=args,
            )
            if not _allowed:
                _last_msg_preview = ((user_text or "").strip())[:80]
                print(
                    f"[Pipeline] Tool: update_person_name REJECTED (intent) "
                    f"— {_reason}; user_text: '{_last_msg_preview}'"
                )
                _log_intent_divergence(
                    tool_name="update_person_name",
                    sidecar=intent_sidecar,
                    gate_decision=f"reject: {_reason}",
                    user_text=user_text, person_id=person_id,
                )
                return "rejected"
            print(
                f"[Pipeline] Tool: update_person_name allowed by intent "
                f"gate — {_reason}"
            )
            _log_intent_divergence(
                tool_name="update_person_name",
                sidecar=intent_sidecar,
                gate_decision="allow",
                user_text=user_text, person_id=person_id,
            )
        elif INTENT_FALLBACK_TO_REGEX:
            if not _user_text_gate_passes(
                user_text, new_name, PERSON_NAME_ASSIGN_PATTERNS
            ):
                _last_msg_preview = ((user_text or "").strip())[:80]
                print(
                    f"[Pipeline] Tool: update_person_name REJECTED "
                    f"(regex fallback) — user did not self-identify as "
                    f"'{new_name}' in: '{_last_msg_preview}'"
                )
                _log_intent_divergence(
                    tool_name="update_person_name",
                    sidecar=None,
                    gate_decision="regex_fallback_reject",
                    user_text=user_text, person_id=person_id,
                )
                return "rejected"
            _log_intent_divergence(
                tool_name="update_person_name",
                sidecar=None,
                gate_decision="regex_fallback_allow",
                user_text=user_text, person_id=person_id,
            )
        else:
            # Both classifier unavailable AND fallback disabled — this
            # state only happens after P1.17 flips the fallback off AND
            # the classifier genuinely failed (timeout / parse). Silent
            # drop would feel broken; log loudly and allow so legitimate
            # mutation tools aren't blackholed on infrastructure blips.
            print(
                f"[Pipeline] WARN: update_person_name — classifier "
                f"unavailable AND fallback disabled; allowing with warning"
            )
            _log_intent_divergence(
                tool_name="update_person_name",
                sidecar=None,
                gate_decision="both_unavailable_allow_with_warning",
                user_text=user_text, person_id=person_id,
            )

    if new_name and new_name.lower() != person_name.lower():
        # Session 100 Bug F — enrollment-mishear escape hatch. When a
        # fresh-enrollment session (face only, no voice corroboration) sees
        # a grounded rename claim, allow it through the stranger-promotion
        # chain instead of flipping to disputed. 2026-04-23 canary: STT
        # mishear at first boot wrote "Gevan" instead of "Jagan"; the
        # classic dispute-flip locked the wrong name in place for the
        # whole session + cascaded into all downstream facts. The classifier
        # gate above has already validated the rename is grounded
        # (assign_own_name intent + user_text match); this branch only
        # decides the ROUTING between dispute-flip and promotion-rename.
        if (
            _sess_type in ("known", "best_friend")
            and _is_enrollment_mishear_candidate(db, person_id, _exec_snap)
        ):
            if db:
                db.update_person_name(person_id, new_name)
                _invalidate_bf_cache()  # Session 115 Fix 2 — rename may target bf
            old_pat_mh = re.compile(r'\b' + re.escape(person_name) + r'\b', re.IGNORECASE)
            for msg in _conversation_store.peek_history(person_id):
                msg["content"] = old_pat_mh.sub(new_name, msg["content"])
            if _wiring._session_store.peek_snapshot(person_id) is not None:
                # P0.S7.5 D3 — await rename synchronously (was create_task);
                # downstream canonical-ack peek_snapshot observes new name.
                try:
                    await _wiring._session_store.rename(person_id, new_name)
                except Exception as _rn_e:
                    print(f"[Pipeline] _session_store.rename failed: {_rn_e!r}")  # OPTIONAL
            # Session 102 Bug F.3: refresh in-frame cache immediately.
            try:
                asyncio.get_running_loop().create_task(
                    _presence_store.update_name(person_id, new_name)
                )
            except RuntimeError:
                pass  # OPTIONAL: no running loop in test/early-boot context
            # Migrate knowledge rows + rebuild graph. NOTE: person_type
            # stays as-is (best_friend keeps best_friend; known keeps
            # known) — this is a NAME correction, not a privilege change.
            if _wiring._brain_orchestrator:
                _wiring._brain_orchestrator.on_identity_confirmed(person_id, person_name, new_name)
            print(
                f"[Pipeline] Enrollment-mishear rename: {person_name!r} → "
                f"{new_name!r} (person_type={_sess_type!r} preserved; "
                f"session fresh + no voice corroboration)"
            )
            return "handled"

        # A rename on an already-KNOWN session is structurally suspicious —
        # the sensor may have misidentified the speaker. Do NOT rename the DB
        # row (that would corrupt the known person's identity). Flip to
        # "disputed": extraction pauses, next turn's SENSOR block surfaces
        # the mismatch, and the user can clarify before anything is persisted.
        # Any enrolled-identity session ("known" OR "best_friend") gets the
        # same dispute-flip treatment — a rename here is structurally suspicious
        # (sensor may be poisoned) and we MUST NOT touch the DB, since the pid
        # belongs to a real enrolled person whose identity the system has to
        # protect. best_friend is especially critical because they're the system
        # owner: a mis-rename would transfer their privileges to the attacker.
        if _sess_type in ("known", "best_friend"):
            if _wiring._session_store.peek_snapshot(person_id) is not None:
                _dispute_ts = time.time()                # WALLCLOCK: persisted watchdog display (dispute_set_at :4429)
                _dispute_ts_mono = time.monotonic()      # #5 Slice B (§0.1.3): dispute_set_at_monotonic (DISPUTE_MAX_DURATION elapsed-math)
                try:
                    _loop = asyncio.get_running_loop()
                    _loop.create_task(_wiring._session_store.transition_to_disputed(
                        person_id, new_name,
                        f"speaker claims name '{new_name}', sensor says '{person_name}'",
                        now=_dispute_ts, now_mono=_dispute_ts_mono,
                    ))
                    _loop.create_task(_wiring._session_store.set_cached_prefix(person_id, None))
                except RuntimeError:
                    pass  # OPTIONAL: no running loop in test/early-boot context
            if _wiring._brain_orchestrator:
                _wiring._brain_orchestrator.mark_disputed(person_id)
            print(
                f"[Pipeline] Tool: identity DISPUTED — speaker claims '{new_name}', "
                f"sensor said '{person_name}' (session was {_sess_type!r}). "
                f"Extraction paused for this session."
            )
            return "handled"

        # Finding G — CRITICAL: a rename on a DISPUTED session must NOT touch
        # the DB. The disputed pid belongs to the sensor-matched (real) person
        # whom vision wrongly matched; renaming their row would permanently
        # overwrite their identity. Block the rename and keep the dispute
        # active — it will force-close via DISPUTE_MAX_DURATION, and the user
        # can audit+repair the poisoned gallery (audit_person.py / repair_gallery.py)
        # or factory-reset if the drift is severe.
        if _is_disputed(person_id):
            # N3 — count persistent blocks and surface a watchdog alert once the
            # count crosses DISPUTE_RENAME_BLOCK_THRESHOLD. `disputed_block_alerted`
            # prevents re-firing within the same session; both fields evaporate
            # when _close_session pops the session dict.
            _block_count = (_exec_snap.disputed_block_count if _exec_snap is not None else 0) + 1
            try:
                _loop = asyncio.get_running_loop()
                _loop.create_task(_wiring._session_store.increment_block_count(person_id))
            except RuntimeError:
                pass  # OPTIONAL: no running loop in test/early-boot context
            print(
                f"[Pipeline] Tool: disputed-session rename to '{new_name}' BLOCKED "
                f"(block #{_block_count}) — pid '{person_id}' belongs to '{person_name}' "
                f"(sensor-matched), not the current speaker. Skipping DB rename; "
                f"dispute stays active until timeout or session end."
            )
            if (_block_count >= DISPUTE_RENAME_BLOCK_THRESHOLD
                    and not (_exec_snap.disputed_block_alerted if _exec_snap is not None else False)
                    and _wiring._brain_orchestrator):
                try:
                    _loop = asyncio.get_running_loop()
                    _loop.create_task(_wiring._session_store.mark_block_alerted(person_id))
                except RuntimeError:
                    pass  # OPTIONAL: no running loop in test/early-boot context
                # prior_person_type tells us whether this is a "best_friend"
                # impersonation (critical) or a general "known" one (warning).
                _victim_type = (_exec_snap.prior_person_type if _exec_snap is not None else None) or "stranger"
                _wiring._brain_orchestrator.report_dispute_rename_burst(
                    victim_pid=person_id,
                    victim_name=person_name,
                    victim_person_type=_victim_type,
                    claimed_name=new_name,
                    block_count=_block_count,
                    dispute_started_at=_exec_snap.dispute_set_at if _exec_snap is not None else None,
                )
            return "handled"

        # Stranger session: legitimate rename path (the pid was minted for this
        # stranger, so renaming it is the intended promotion to a real name).
        if db:
            db.update_person_name(person_id, new_name)
            _invalidate_bf_cache()  # Session 115 Fix 2 — defensive (stranger rename shouldn't touch bf, but cheap)
        # Retroactively fix old name in in-memory history
        old_pat = re.compile(r'\b' + re.escape(person_name) + r'\b', re.IGNORECASE)
        for msg in _conversation_store.peek_history(person_id):
            msg["content"] = old_pat.sub(new_name, msg["content"])
        # P0.S7.5 D3 — await rename synchronously so the downstream
        # canonical-ack template peek_snapshot observes the new name.
        # Previous fire-and-forget create_task was racy (canary 2026-05-19
        # 21:04:24 "Got it, visitor." instead of "Got it, Lexi.").
        try:
            await _wiring._session_store.rename(person_id, new_name)
        except Exception as _rn_e:
            # Preserve graceful-degrade semantic; rename failure does
            # NOT propagate into a turn crash. Known limitation per
            # Plan v2 OBS A: in the rare rename-failure case, the
            # downstream canonical ack speaks the old name.
            print(f"[Pipeline] _session_store.rename failed: {_rn_e!r}")  # OPTIONAL
        # Session 102 Bug F.3: refresh in-frame cache immediately.
        try:
            asyncio.get_running_loop().create_task(
                _presence_store.update_name(person_id, new_name)
            )
        except RuntimeError:
            pass  # OPTIONAL: no running loop in test/early-boot context
        # Stranger identity confirmed via LLM tool: run full promotion chain
        if _sess_type == "stranger":
            if db:
                db.update_person_type(person_id, "known")
            if _wiring._brain_orchestrator:
                _wiring._brain_orchestrator.on_identity_confirmed(person_id, person_name, new_name)
            try:
                _loop = asyncio.get_running_loop()
                _loop.create_task(_wiring._session_store.promote_type(person_id, "known"))
                _loop.create_task(_wiring._session_store.set_cached_prefix(person_id, None))
                _loop.create_task(_wiring._session_store.set_waiting_for_name(person_id, False))
            except RuntimeError:
                pass  # OPTIONAL: no running loop in test/early-boot context
        print(f"[Pipeline] Tool: person name '{person_name}' → '{new_name}'")
        return "handled"
    # Same name — no-op. Bug Q (2026-04-21): return "handled_noop" so the
    # caller does NOT emit the canonical "Got it, {name}." ack. Writing
    # that ack to history when nothing actually changed was the feedback
    # loop that had the LLM re-issue the same tool call across turns.
    print(f"[Pipeline] Tool: update_person_name no-op (already '{person_name}')")
    return "handled_noop"
async def _handle_report_identity_mismatch(args: dict, ctx: "_ToolContext") -> "str | None":
    """P0.8 extracted handler — verbatim move of report_identity_mismatch branch from _execute_tool."""
    # P0.8 mechanical extraction (handler body is verbatim from the original
    # _execute_tool branch).  Local names rebind from ctx so the body reads
    # identically.  Intent + grounding gates stay inside — P1.A3 extracts
    # them next.
    args           = ctx.args
    person_id      = ctx.person_id
    person_name    = ctx.person_name
    db             = ctx.db
    user_text      = ctx.user_text
    intent_sidecar = ctx.intent_sidecar
    _exec_snap     = ctx.exec_snap

    # Bug G3 (2026-04-22 live run): the second-biggest blast-radius tool
    # was the only Session 71+ side-effect tool without a user-text gate.
    # Jagan's legit multi-person scene question "who are you talking to?"
    # was interpreted as identity denial by the LLM → session flipped
    # DISPUTED → ~15 broken turns. Gate requires a denial-signal phrase.
    # Session 86 P1.7b: classifier-first; regex fallback on classifier
    # unavail. Same 3-branch pattern as update_person_name (P1.7a canary).
    from core.config import INTENT_FALLBACK_TO_REGEX
    if intent_sidecar is not None:
        _allowed, _reason = _intent_allows(
            tool_name="report_identity_mismatch",
            turn_intent=intent_sidecar.get("turn_intent") or "",
            confidence=float(intent_sidecar.get("confidence") or 0.0),
            extracted_value=intent_sidecar.get("extracted_value"),
            user_text=user_text,
            tool_args=args,
        )
        if not _allowed:
            _last_msg_preview = ((user_text or "").strip())[:80]
            print(
                f"[Pipeline] Tool: report_identity_mismatch REJECTED (intent) "
                f"— {_reason}; user_text: '{_last_msg_preview}'"
            )
            _log_intent_divergence(
                tool_name="report_identity_mismatch",
                sidecar=intent_sidecar,
                gate_decision=f"reject: {_reason}",
                user_text=user_text, person_id=person_id,
            )
            return "rejected"
        print(
            f"[Pipeline] Tool: report_identity_mismatch allowed by intent "
            f"gate — {_reason}"
        )
        _log_intent_divergence(
            tool_name="report_identity_mismatch",
            sidecar=intent_sidecar,
            gate_decision="allow",
            user_text=user_text, person_id=person_id,
        )
    elif INTENT_FALLBACK_TO_REGEX:
        if not _user_text_gate_passes(user_text, None, IDENTITY_DENIAL_PATTERNS):
            _last_msg_preview = ((user_text or "").strip())[:80]
            print(
                f"[Pipeline] Tool: report_identity_mismatch REJECTED "
                f"(regex fallback) — user did not deny identity in: "
                f"'{_last_msg_preview}'"
            )
            _log_intent_divergence(
                tool_name="report_identity_mismatch",
                sidecar=None,
                gate_decision="regex_fallback_reject",
                user_text=user_text, person_id=person_id,
            )
            return "rejected"
        _log_intent_divergence(
            tool_name="report_identity_mismatch",
            sidecar=None,
            gate_decision="regex_fallback_allow",
            user_text=user_text, person_id=person_id,
        )
    else:
        print(
            f"[Pipeline] WARN: report_identity_mismatch — classifier "
            f"unavailable AND fallback disabled; allowing with warning"
        )
        _log_intent_divergence(
            tool_name="report_identity_mismatch",
            sidecar=None,
            gate_decision="both_unavailable_allow_with_warning",
            user_text=user_text, person_id=person_id,
        )

    reason = (args.get("reason") or "").strip() or "identity mismatch reported"
    if _wiring._session_store.peek_snapshot(person_id) is not None:
        _dispute_ts_ridm = time.time()                   # WALLCLOCK: persisted watchdog display (dispute_set_at :4429)
        _dispute_ts_ridm_mono = time.monotonic()         # #5 Slice B (§0.1.3): dispute_set_at_monotonic (DISPUTE_MAX_DURATION)
        try:
            _loop = asyncio.get_running_loop()
            _loop.create_task(_wiring._session_store.transition_to_disputed(
                person_id, None, reason, now=_dispute_ts_ridm, now_mono=_dispute_ts_ridm_mono,
            ))
            _loop.create_task(_wiring._session_store.set_cached_prefix(person_id, None))
        except RuntimeError:
            pass  # OPTIONAL: no running loop in test/early-boot context
    if _wiring._brain_orchestrator:
        _wiring._brain_orchestrator.mark_disputed(person_id)
    print(f"[Pipeline] Tool: identity DISPUTED for {person_name} — {reason}")
    return "handled"
async def _handle_update_system_name(args: dict, ctx: "_ToolContext") -> "str | None":
    """P0.8 extracted handler — verbatim move of update_system_name branch from _execute_tool."""
    # P0.8 mechanical extraction (handler body is verbatim from the original
    # _execute_tool branch).  Local names rebind from ctx so the body reads
    # identically.  Intent + grounding gates stay inside — P1.A3 extracts
    # them next.
    args           = ctx.args
    person_id      = ctx.person_id
    person_name    = ctx.person_name
    db             = ctx.db
    user_text      = ctx.user_text
    intent_sidecar = ctx.intent_sidecar
    _exec_snap     = ctx.exec_snap

    new_name, _ = sanitize_name(args.get("name") or "")
    if not new_name or new_name.lower() in _INVALID_SYSTEM_NAMES:
        print(f"[Pipeline] Tool: update_system_name rejected invalid name '{new_name}'")
        return None

    # Bug G1 (2026-04-22 live run): Session 71's OR-gate accepted
    # "do you know the GAME called Detroit?" because 'Detroit' appeared in
    # the turn — and the system renamed itself to "Detroit". Session 73
    # tightened to capture-group regex; Session 86 P1.7b layers the
    # classifier gate on top (this is the fix for the 2026-04-22 Alexa
    # bug: "I want it to be changed to Alexa" rejected by regex 3× even
    # though classifier got it right at 0.95 every time).
    from core.config import INTENT_FALLBACK_TO_REGEX
    if intent_sidecar is not None:
        _allowed, _reason = _intent_allows(
            tool_name="update_system_name",
            turn_intent=intent_sidecar.get("turn_intent") or "",
            confidence=float(intent_sidecar.get("confidence") or 0.0),
            extracted_value=intent_sidecar.get("extracted_value"),
            user_text=user_text,
            tool_args=args,
        )
        if not _allowed:
            _last_msg_preview = ((user_text or "").strip())[:80]
            print(
                f"[Pipeline] Tool: update_system_name REJECTED (intent) "
                f"— {_reason}; user_text: '{_last_msg_preview}'"
            )
            _log_intent_divergence(
                tool_name="update_system_name",
                sidecar=intent_sidecar,
                gate_decision=f"reject: {_reason}",
                user_text=user_text, person_id=person_id,
            )
            return "rejected"
        print(
            f"[Pipeline] Tool: update_system_name allowed by intent gate "
            f"— {_reason}"
        )
        _log_intent_divergence(
            tool_name="update_system_name",
            sidecar=intent_sidecar,
            gate_decision="allow",
            user_text=user_text, person_id=person_id,
        )
    elif INTENT_FALLBACK_TO_REGEX:
        if not _user_text_gate_passes(user_text, new_name, SYSTEM_NAME_ASSIGN_PATTERNS):
            _last_msg_preview = ((user_text or "").strip())[:80]
            print(
                f"[Pipeline] Tool: update_system_name REJECTED "
                f"(regex fallback) — user did not assign '{new_name}' in: "
                f"'{_last_msg_preview}'"
            )
            _log_intent_divergence(
                tool_name="update_system_name",
                sidecar=None,
                gate_decision="regex_fallback_reject",
                user_text=user_text, person_id=person_id,
            )
            return "rejected"
        _log_intent_divergence(
            tool_name="update_system_name",
            sidecar=None,
            gate_decision="regex_fallback_allow",
            user_text=user_text, person_id=person_id,
        )
    else:
        print(
            f"[Pipeline] WARN: update_system_name — classifier unavailable "
            f"AND fallback disabled; allowing with warning"
        )
        _log_intent_divergence(
            tool_name="update_system_name",
            sidecar=None,
            gate_decision="both_unavailable_allow_with_warning",
            user_text=user_text, person_id=person_id,
        )

    if new_name.lower() != _wiring._pipeline_state_store.peek_active_system_name().lower():
        await _wiring._pipeline_state_store.set_active_system_name(new_name)
        # Invalidate prefix cache for ALL sessions — system_name is in Section 2
        try:
            _loop = asyncio.get_running_loop()
            for _snap_inv in _wiring._session_store.peek_all_snapshots():
                _loop.create_task(_wiring._session_store.set_cached_prefix(_snap_inv.person_id, None))
        except RuntimeError:
            pass  # OPTIONAL
        if _wiring._brain_orchestrator:
            _wiring._brain_orchestrator.set_system_name(new_name)
        if db:
            db.set_system_identity(
                "system_name", new_name,
                set_by=person_id,
                note=f"named by {person_name}",
            )
        print(f"[Pipeline] Tool: system name → '{new_name}'")
        return "handled"
    # Same name — no-op. Bug Q: no canonical ack, no history write.
    # The redundant "Got it, I'll go by Kara." on turns 15/17/19 in the
    # 2026-04-21 run was the direct feedback-loop driver.
    print(f"[Pipeline] Tool: update_system_name no-op (already '{_wiring._pipeline_state_store.peek_active_system_name()}')")
    return "handled_noop"
async def _handle_shutdown(args: dict, ctx: "_ToolContext") -> "str | None":
    """P0.8 extracted handler — verbatim move of shutdown branch from _execute_tool."""
    # P0.8 mechanical extraction (handler body is verbatim from the original
    # _execute_tool branch).  Local names rebind from ctx so the body reads
    # identically.  Intent + grounding gates stay inside — P1.A3 extracts
    # them next.
    args           = ctx.args
    person_id      = ctx.person_id
    person_name    = ctx.person_name
    db             = ctx.db
    user_text      = ctx.user_text
    intent_sidecar = ctx.intent_sidecar
    _exec_snap     = ctx.exec_snap

    # Session 86 P1.7b site 4: classifier-first; 3-regex fallback (strict
    # phrases + lenient goodnight + question-about-shutdown exclusion)
    # kept intact as the safety net. Shutdown is the highest-blast-radius
    # mutation tool so BOTH gates must agree for a shutdown to fire in the
    # dual-gate phase. ``request_shutdown`` requires INTENT_SHUTDOWN_CONF_MIN
    # (0.80), strictly higher than the general 0.75 floor — wired via the
    # tool_name branch in _intent_allows.
    from core.config import INTENT_FALLBACK_TO_REGEX
    _last_msg = (user_text or "").lower()
    _SHUTDOWN_STRICT = (
        "shut down", "shutdown", "turn off", "go to sleep", "stop listening",
        "bye i'm done", "power off", "switch off",
    )
    _SHUTDOWN_LENIENT_RE = re.compile(
        r"^\s*(?:good\s?night|i'?m\s+done|i\s+am\s+done)\s*[!.?]*\s*$"
    )

    def _regex_says_shutdown(msg: str) -> bool:
        """Legacy 3-regex chain — strict phrases + lenient goodnight
        minus question-about-shutdown exclusion. Extracted so the
        fallback branch reads cleanly and the shared logic is in one
        place."""
        has_phrase = (
            any(re.search(r'\b' + re.escape(p) + r'\b', msg) for p in _SHUTDOWN_STRICT)
            or bool(_SHUTDOWN_LENIENT_RE.match(msg))
        )
        is_question = has_phrase and _SHUTDOWN_QUESTION_RE.search(msg)
        return bool(msg and has_phrase and not is_question)

    if intent_sidecar is not None:
        _allowed, _reason = _intent_allows(
            tool_name="shutdown",
            turn_intent=intent_sidecar.get("turn_intent") or "",
            confidence=float(intent_sidecar.get("confidence") or 0.0),
            extracted_value=intent_sidecar.get("extracted_value"),
            user_text=user_text,
            tool_args=args,
        )
        if not _allowed:
            print(
                f"[Pipeline] Tool: shutdown REJECTED (intent) — {_reason}; "
                f"user_text: '{_last_msg[:80]}'"
            )
            _log_intent_divergence(
                tool_name="shutdown",
                sidecar=intent_sidecar,
                gate_decision=f"reject: {_reason}",
                user_text=user_text, person_id=person_id,
            )
            return "rejected"
        print(f"[Pipeline] Tool: shutdown allowed by intent gate — {_reason}")
        _log_intent_divergence(
            tool_name="shutdown",
            sidecar=intent_sidecar,
            gate_decision="allow",
            user_text=user_text, person_id=person_id,
        )
    elif INTENT_FALLBACK_TO_REGEX:
        if not _regex_says_shutdown(_last_msg):
            print(
                f"[Pipeline] Tool: shutdown REJECTED (regex fallback) — "
                f"no explicit command in: '{_last_msg[:80]}'"
            )
            _log_intent_divergence(
                tool_name="shutdown",
                sidecar=None,
                gate_decision="regex_fallback_reject",
                user_text=user_text, person_id=person_id,
            )
            return "rejected"
        _log_intent_divergence(
            tool_name="shutdown",
            sidecar=None,
            gate_decision="regex_fallback_allow",
            user_text=user_text, person_id=person_id,
        )
    else:
        # Shutdown's both-unavailable policy diverges from the other
        # mutation tools: allow-with-warning would risk an unintended
        # system shutdown if the classifier blips. For the biggest-
        # blast-radius tool we fail CLOSED — user can retry their
        # command in ~10s once the classifier recovers.
        print(
            f"[Pipeline] WARN: shutdown — classifier unavailable AND "
            f"fallback disabled; REJECTING (fail-closed for highest "
            f"blast radius)"
        )
        _log_intent_divergence(
            tool_name="shutdown",
            sidecar=None,
            gate_decision="both_unavailable_reject_failclosed",
            user_text=user_text, person_id=person_id,
        )
        return "rejected"
    print("[Pipeline] Tool: shutdown requested")
    return "shutdown"
async def _handle_search_memory(args: dict, ctx: "_ToolContext") -> "str | None":
    """P0.8 extracted handler — verbatim move of search_memory branch from _execute_tool."""
    # P0.8 mechanical extraction (handler body is verbatim from the original
    # _execute_tool branch).  Local names rebind from ctx so the body reads
    # identically.  Intent + grounding gates stay inside — P1.A3 extracts
    # them next.
    args           = ctx.args
    person_id      = ctx.person_id
    person_name    = ctx.person_name
    db             = ctx.db
    user_text      = ctx.user_text
    intent_sidecar = ctx.intent_sidecar
    _exec_snap     = ctx.exec_snap

    # Normally handled inside ask_stream (brain.py). This branch fires only in
    # degraded paths (SICK state non-streaming). Graceful no-op.
    print("[Pipeline] Tool: search_memory fallback — not executed in degraded mode")
    return None
# P0.8: dispatch table — single source of truth for tool→handler mapping.
# _execute_tool looks up the handler here, then wraps the call in
# asyncio.wait_for with a per-tool budget from TOOL_TIMEOUT_OVERRIDES.
# Adding a new tool: define _handle_<name>, register here, add a
# TOOL_TIMEOUT_OVERRIDES entry if its budget differs from TOOL_TIMEOUT_SECS.
_TOOL_HANDLERS: "dict[str, object]" = {
    "update_person_name":       _handle_update_person_name,
    "report_identity_mismatch": _handle_report_identity_mismatch,
    "update_system_name":       _handle_update_system_name,
    "shutdown":                 _handle_shutdown,
    "search_memory":            _handle_search_memory,
}
async def _execute_tool(
    name: str,
    args: dict,
    person_id: str,
    person_name: str,
    db: "FaceDB",
    user_text: str = "",
    intent_sidecar: "dict | None" = None,
) -> str | None:
    """
    Execute a single tool call from the LLM.

    ``intent_sidecar`` (VISION_ROADMAP P1.7a): the shadow classifier's sidecar
    dict from ``_classify_intent`` if it ran this turn, or ``None`` when the
    classifier wasn't consulted (tool not in TOOL_INTENT_MAP, shadow mode
    disabled, timeout, parse failure). Gated-tool handlers consult the sidecar
    first via ``_intent_allows``; when the sidecar is ``None``,
    ``INTENT_FALLBACK_TO_REGEX=True`` routes through the legacy regex gate
    (safety net until ≥30 real_observed samples validate the classifier
    enough to flip fallback to False at P1.17). All gate decisions are
    persisted to ``brain.db.intent_divergences`` for Phase 5 drift detection.

    Return status classifies the result:
      "shutdown"      — shutdown was requested (caller triggers shutdown).
      "handled"       — tool ran AND changed state; caller may emit a canonical ack.
      "handled_noop"  — tool ran but was a no-op (state already matched); caller
                        must NOT emit a canonical ack to avoid the feedback loop
                        observed in Bug Q (LLM hears "Got it, I'll go by Kara" on
                        every redundant call and re-issues it next turn).
      "unknown"       — Bug P (2026-04-21): the LLM emitted a tool name that
                        isn't in our registry (typically echoing a user word,
                        e.g. ``Buddy({})``). Model artifact, NOT a security
                        violation. Caller treats it as "no tool effect".
      "rejected"      — Session 71 (Bugs S / T, 2026-04-21): server-side
                        user-text gate rejected the call. The LLM wanted to act
                        but the user's actual utterance didn't support it
                        (e.g. update_system_name('Kara') when user asked "do
                        you know Detroit?"). Distinct from "unknown" (tool
                        doesn't exist) and None (privilege denied / internal
                        error). Both "rejected" and "unknown" route through the
                        same Ollama-text retry path in conversation_turn.
      "tool_timeout"  — P0.8 (2026-05-16): handler exceeded its per-tool wall-clock
                        budget (TOOL_TIMEOUT_OVERRIDES or TOOL_TIMEOUT_SECS).
                        asyncio.wait_for cancelled the task; transaction
                        wrappers rolled back any partial SQL state via __aexit__.
                        Routes through the same retry path as "rejected" /
                        "unknown" with a tool-timeout system_note.
      None            — blocked by privilege gate, repeat guard, or internal error.
    """
    # ── Layer 0: Unknown-tool filter (Bug P, 2026-04-21 live run) ────────────
    # TOOL_PRIVILEGES is the canonical registry — a startup assertion ties every
    # `brain.TOOLS` entry to a row here, so "not in table" means the LLM invented
    # a tool name (hallucination from prompt echo). These are model artifacts,
    # not security violations, and must NOT hit the BLOCKED logging path — the
    # user only sees the downstream "Sorry, I missed that" filler, which is worse
    # UX than silently discarding the phantom call and letting streamed text
    # (or an Ollama retry) flow through.
    if name not in TOOL_PRIVILEGES:
        print(f"[Pipeline] Tool: {name!r} — unknown tool, discarded (LLM hallucination)")
        return "unknown"

    # ── Layer 3: Tool repeat guard ────────────────────────────────────────────
    # Abort if the same (tool, args) fires TOOL_REPEAT_MAX_CONSECUTIVE times in
    # a row with no user message in between — prevents infinite loop scenarios.
    import hashlib as _hl, json as _j
    _args_hash  = _hl.md5(_j.dumps(args, sort_keys=True, default=str).encode()).hexdigest()[:8]
    _repeat_key = f"{name}:{_args_hash}"
    _session_snap_rg = _wiring._session_store.peek_snapshot(person_id)
    if _session_snap_rg is not None and _session_snap_rg.tool_repeat_last == _repeat_key:
        _new_count = _session_snap_rg.tool_repeat_count + 1
        if _new_count >= TOOL_REPEAT_MAX_CONSECUTIVE:
            print(
                f"[Pipeline] WARN: Tool repeat guard — '{name}' fired {_new_count}x "
                f"consecutively with same args. Aborting to prevent loop."
            )
            try:
                _loop = asyncio.get_running_loop()
                _loop.create_task(_wiring._session_store.update_tool_repeat(person_id, None, 0))
            except RuntimeError:
                pass  # OPTIONAL: no running loop in test/early-boot context
            return None
        try:
            _loop = asyncio.get_running_loop()
            _loop.create_task(_wiring._session_store.update_tool_repeat(person_id, _repeat_key, _new_count))
        except RuntimeError:
            pass  # OPTIONAL: no running loop in test/early-boot context
    else:
        if _session_snap_rg is not None:
            try:
                _loop = asyncio.get_running_loop()
                _loop.create_task(_wiring._session_store.update_tool_repeat(person_id, _repeat_key, 1))
            except RuntimeError:
                pass  # OPTIONAL: no running loop in test/early-boot context

    # ── Privilege gate ────────────────────────────────────────────────────────
    # Table-driven (see TOOL_PRIVILEGES in core/config.py). No hardcoded
    # `if name == "shutdown" ...` checks — privilege policy is data, changing
    # it is a config edit with no code change here or in brain.py.
    # Fallback is "stranger" (most restricted) if the session dict is somehow
    # missing person_type — fail-safe rather than fail-open.
    _exec_snap   = _wiring._session_store.peek_snapshot(person_id)
    _caller_type = _exec_snap.person_type if _exec_snap is not None else "stranger"
    if not _tool_allowed(name, _caller_type):
        allowed = TOOL_PRIVILEGES.get(name, frozenset())
        print(
            f"[Pipeline] Tool: {name!r} BLOCKED for {person_name} "
            f"(person_type={_caller_type!r}) — allowed: {sorted(allowed) or '<not in table — always blocked>'}"
        )
        return None

    # P0.8: context bundle passed to extracted handlers.  Built once after
    # all pre-dispatch gates pass; carries the per-call inputs and derived
    # state.  Handler signature is async (args, ctx) — matches the dispatch
    # table _TOOL_HANDLERS that P0.8-7 wires up via asyncio.wait_for.
    _ctx = _ToolContext(
        args=args,
        person_id=person_id,
        person_name=person_name,
        db=db,
        user_text=user_text,
        intent_sidecar=intent_sidecar,
        exec_snap=_exec_snap,
        caller_type=_caller_type,
    )

    # P0.8: dispatch table + per-tool timeout.  asyncio.wait_for wraps ONLY
    # the handler invocation; Layer 0 / repeat / privilege gates above it
    # run un-budgeted (they're micro-operations).  On TimeoutError, the
    # handler task is cancelled and CancelledError propagates through
    # transaction wrappers (FaceDB.transaction / BrainDB._safe_commit
    # __aexit__) — partial SQL writes roll back automatically.
    # P0.0.7 H7 — emit tool_call event BEFORE dispatch via safe_emit_sync.
    # The writer task's _flush_one assigns an id, records it in
    # _recent_parent under (session_id=person_id, event_type="tool_call");
    # the tool_result event below auto-resolves parent_event_id via
    # NATURAL_PARENT_PAIRS. Single P0.4-annotated except in safe_emit_sync.
    from core.event_log import safe_emit_sync, ToolCallPayload
    safe_emit_sync(
        "tool_call",
        ToolCallPayload(
            name=name,
            args=dict(args or {}),
            person_id=person_id,
            intent_sidecar=dict(intent_sidecar) if intent_sidecar else None,
        ),
        session_id=person_id,
    )

    handler = _TOOL_HANDLERS.get(name)
    if handler is None:
        _tool_result_status = None  # defensive — tool in registry but no handler
        _tool_result_error: "str | None" = "no_handler_registered"
    else:
        _timeout = TOOL_TIMEOUT_OVERRIDES.get(name, TOOL_TIMEOUT_SECS)
        _tool_result_error = None
        try:
            _tool_result_status = await asyncio.wait_for(handler(args, _ctx), timeout=_timeout)
        except asyncio.TimeoutError:
            print(
                f"[Pipeline] Tool: {name!r} TIMEOUT after {_timeout}s "
                f"(person={person_name!r}). Task cancelled; partial SQL state "
                f"rolled back via transaction __aexit__. Routing to retry path."
            )
            _tool_result_status = "tool_timeout"
            _tool_result_error = f"asyncio.TimeoutError after {_timeout}s"

    # P0.0.7 H7 — emit tool_result event AFTER dispatch (single emit
    # location for D7 N=1) via safe_emit_sync. parent_event_id
    # auto-resolves via NATURAL_PARENT_PAIRS to the tool_call event above.
    from core.event_log import safe_emit_sync, ToolResultPayload
    safe_emit_sync(
        "tool_result",
        ToolResultPayload(
            status=str(_tool_result_status) if _tool_result_status is not None else "none",
            response_text=None,
            error=_tool_result_error,
        ),
        session_id=person_id,
    )

    return _tool_result_status
