"""
sim_runner.py — Headless conversation simulator for dog-ai.

Drives pipeline.conversation_turn() directly — no camera, no STT.
TTS audio plays normally through speakers.

Usage:
    python sim_runner.py turns_10_owner_only.txt   # multi-person batch
    python sim_runner.py turns_01.txt              # legacy single-person batch
    python sim_runner.py --close-session           # close sim session cleanly

═══════════════════════════════════════════════════════════════════════════════
Multi-person turn file format
═══════════════════════════════════════════════════════════════════════════════

    !CAST
      JAGAN     id=sim_jagan    name=Jagan    type=best_friend
      KAVYA     id=sim_kavya    name=Kavya    type=known
      STRANGER  id=stranger_s1  name=visitor  type=stranger
    !END_CAST

    # Hash lines are comments — stripped before processing

    ---ENTER JAGAN                  # person steps into frame, session opens
    ---ENTER KAVYA                  # second person enters
    [JAGAN] Hey Kara, how are you?  # single-speaker turn
    [KAVYA] Hi there!               # another speaker's turn
    [JAGAN|KAVYA] Hello! | Hi!      # within-utterance diarization (split at |)
    ---LEAVE KAVYA                  # person leaves frame (session stays briefly)
    ---CLOSE JAGAN                  # session ends cleanly (notify_session_end)
    ---CLOSE_ALL                    # close every open session
    ---PAUSE 2.0                    # asyncio.sleep (test timing/KAIROS)
    ---SILENCE                      # no speech event (KAIROS testing)
    ---ASSERT SESSION_OPEN JAGAN    # inline test assertion
    ---ASSERT SESSION_CLOSED KAVYA
    ---ASSERT WAITING_FOR_NAME STRANGER
    ---ASSERT GATE_CLEARED STRANGER

Stranger IDs must start with "stranger_" (pipeline uses startswith check).

═══════════════════════════════════════════════════════════════════════════════
Legacy single-person format (backward compat — no !CAST block)
═══════════════════════════════════════════════════════════════════════════════

    # lines starting with # are skipped
    Hi Kara, my name is Jagan
    I'm a software engineer
    ...
"""

import asyncio
import argparse
import json
import pathlib
import re
import sys
import time

# ── Ensure UTF-8 output ───────────────────────────────────────────────────────
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import pipeline
import runtime.wiring as _wiring
from pipeline import (
    conversation_turn,
    PipelineState,
    CloudState,
)
from core.db import FaceDB
from core.config import FACES_DIR, DEFAULT_SYSTEM_NAME, STRANGER_REQUIRE_SYSTEM_NAME
import pathlib as _pathlib

# ── Isolated sim storage — never touches production faces/ directory ───────────
# All sim data lives in faces_sim/ so factory reset and real-world runs are
# completely independent.  Production faces/brain.db is never written by sim.
SIM_FACES_DIR   = _pathlib.Path(__file__).parent / "faces_sim"
SIM_FACES_DIR.mkdir(exist_ok=True)
SIM_DB_PATH     = SIM_FACES_DIR / "faces.db"
SIM_FAISS_PATH  = SIM_FACES_DIR / "faiss.index"
SIM_BRAIN_PATH  = SIM_FACES_DIR / "brain.db"
SIM_GRAPH_PATH  = SIM_FACES_DIR / "brain_graph"
from core.audio import preload_models
from core import voice as voice_mod
from core.brain_agent import BrainOrchestrator
from core.emotion import EmotionAgent

# ── Legacy single-person constants (used when no !CAST block) ─────────────────
_LEGACY_PERSON_ID   = "sim_jagan"
_LEGACY_PERSON_NAME = "Jagan"

# ── Invalid system name guard ─────────────────────────────────────────────────
_INVALID_SYSTEM_NAMES = frozenset({
    "none", "unknown", "unnamed", "noname", "null", "undefined", "n_a", "na"
})

# ── Session state file ────────────────────────────────────────────────────────
_STATE_FILE = pathlib.Path(__file__).parent / "sim_session_state.json"


# ═══════════════════════════════════════════════════════════════════════════════
# Turn file parsing
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_cast_block(lines: list[str]) -> dict[str, dict]:
    """Parse !CAST...!END_CAST block. Returns handle → entry dict."""
    in_cast = False
    cast: dict[str, dict] = {}
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if stripped == "!CAST":
            in_cast = True
            continue
        if stripped == "!END_CAST":
            in_cast = False
            continue
        if not in_cast or not stripped:
            continue
        # Parse: HANDLE  key=value  key=value ...
        parts = stripped.split()
        handle = parts[0].upper()
        entry: dict = {
            "person_id":    None,
            "person_name":  handle.capitalize(),
            "person_type":  "known",
            "face_id":      None,
            "in_frame":     False,
            "session_open": False,
        }
        for part in parts[1:]:
            if "=" in part:
                k, v = part.split("=", 1)
                if k == "id":
                    entry["person_id"] = v
                elif k == "name":
                    entry["person_name"] = v
                elif k == "type":
                    entry["person_type"] = v
                elif k == "face_id":
                    entry["face_id"] = v
        if entry["person_id"] is None:
            raise ValueError(f"!CAST entry '{handle}' missing id= field")
        # Validate stranger IDs
        if entry["person_type"] == "stranger" and not entry["person_id"].startswith("stranger_"):
            raise ValueError(
                f"Stranger '{handle}' id must start with 'stranger_' "
                f"(got '{entry['person_id']}'). Pipeline uses startswith('stranger_') gate."
            )
        cast[handle] = entry
    if not cast:
        raise ValueError("!CAST block is empty or missing")
    return cast


def _parse_turn_file(path: pathlib.Path) -> tuple[dict | None, list[tuple[str, str]]]:
    """
    Parse a turn file. Returns (cast_or_None, events).

    events is a list of (type, payload) tuples:
        ("turn",      "[JAGAN] Hey Kara")
        ("multi",     "[JAGAN|KAVYA] Hello! | Hi!")
        ("directive", "---ENTER JAGAN")
        ("legacy",    "plain text line")   ← old format without speaker tags

    Returns cast=None if no !CAST block (legacy mode).
    """
    raw = path.read_text(encoding="utf-8").splitlines()
    # Strip comments and blank lines
    lines = [l for l in raw if l.strip() and not l.strip().startswith("#")]

    # Detect format
    has_cast = any(l.strip() == "!CAST" for l in lines)
    if not has_cast:
        # Legacy: all non-comment lines are turns
        events = [("legacy", l.strip()) for l in lines if l.strip()]
        return None, events

    # Multi-person: parse cast block first
    cast = _parse_cast_block(raw)

    # Parse events (skip !CAST block itself)
    events: list[tuple[str, str]] = []
    in_cast = False
    _TURN_RE = re.compile(r"^\[([A-Z][A-Z0-9_|]*)\]\s+(.+)$")
    for line in raw:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped in ("!CAST", "!END_CAST"):
            in_cast = stripped == "!CAST"
            continue
        if in_cast:
            continue
        if stripped.startswith("---"):
            events.append(("directive", stripped))
        elif m := _TURN_RE.match(stripped):
            handle_part = m.group(1)
            text_part   = m.group(2).strip()
            if "|" in handle_part and handle_part.count("|") >= 1:
                events.append(("multi", stripped))
            else:
                events.append(("turn", stripped))
        else:
            raise ValueError(
                f"Unrecognised line in multi-person file: {stripped!r}\n"
                "Expected [HANDLE] text, ---DIRECTIVE, or a comment."
            )

    return cast, events


# ═══════════════════════════════════════════════════════════════════════════════
# Session management
# ═══════════════════════════════════════════════════════════════════════════════

def _open_sim_session_for(entry: dict, db: FaceDB) -> None:
    """Open a pipeline session for one cast entry."""
    pid   = entry["person_id"]
    pname = entry["person_name"]
    ptype = entry["person_type"]
    now   = time.time()

    # Ensure person exists in DB
    if ptype == "stranger":
        # Strangers are NOT added to DB at enter time — only when they say the
        # system name (G4 gate clears → progressive enrollment).  We track this
        # with db_enrolled in the session dict.
        pass
    else:
        db.add_person(pid, pname, person_type=ptype)

    if pid in pipeline._active_sessions:
        # Already open — just refresh heartbeat
        pipeline._active_sessions[pid]["last_face_seen"] = now
        pipeline._active_sessions[pid]["last_spoke_at"]  = now
    else:
        print(f"[Sim] Session open: {pid} ({ptype}) — {pname}")
        pipeline._active_sessions[pid] = {
            "person_id":          pid,
            "person_name":        pname,
            "session_type":       "sim",
            "person_type":        ptype,
            "waiting_for_name":   STRANGER_REQUIRE_SYSTEM_NAME if ptype == "stranger" else False,
            "last_face_seen":     now,
            "last_spoke_at":      now,
            "voice_confidence":   1.0,
            "started_at":         now,
            "kairos_clock_reset": True,
            "db_enrolled":        False,          # used by G4 progressive enrollment
        }

    # Seed conversation history from DB
    if pid not in pipeline._conversation:
        pipeline._conversation[pid] = db.load_conversation_history(pid)

    entry["in_frame"]     = True
    entry["session_open"] = True


def _close_sim_session_for(entry: dict) -> None:
    """
    Close a pipeline session. Caller must await asyncio.sleep(2.0) after
    to let brain agent drain the session-end task queue.
    """
    pid = entry["person_id"]
    if pipeline._brain_orchestrator:
        pipeline._brain_orchestrator.notify_session_end(pid)
    pipeline._close_session(pid)
    pipeline._conversation.pop(pid, None)
    entry["in_frame"]     = False
    entry["session_open"] = False
    print(f"[Sim] Session closed: {pid}")


def _heartbeat_in_frame_sessions(cast: dict) -> None:
    """Bump last_face_seen for all in-frame persons — mirrors background vision loop."""
    now = time.time()
    for entry in cast.values():
        if entry["in_frame"] and entry["person_id"] in pipeline._active_sessions:
            pipeline._active_sessions[entry["person_id"]]["last_face_seen"] = now


# ═══════════════════════════════════════════════════════════════════════════════
# Synthetic sensor states
# ═══════════════════════════════════════════════════════════════════════════════

def _build_vision_state(entry: dict, new_face_name: str | None = None) -> dict:
    """Build synthetic vision_state for conversation_turn()."""
    return {
        "face_in_frame": entry["in_frame"],
        "person_name":   entry["person_name"],
        "person_id":     entry["person_id"],
        "new_face":      new_face_name,
    }


def _build_voice_state(entry: dict, voice_confidence: float = 1.0) -> dict:
    """Build synthetic voice_state for conversation_turn()."""
    pid = entry["person_id"]
    return {
        "matched_id":       pid,
        "matched_name":     entry["person_name"],
        "voice_confidence": voice_confidence,
        "matches_active":   pid in pipeline._active_sessions,
    }


def _build_addendum_override(pid: str, db: FaceDB) -> str | None:
    """
    Build prompt_addendum_override exactly as the main pipeline run() loop does
    (pipeline.py lines 2883-2909).

    Combines:
    - Stranger context addendum (if this person is a stranger)
    - Room context (if multiple sessions are active)
    """
    addendum: str | None = None

    # Stranger context — mirrors pipeline.py lines 2884-2896
    if pid.startswith("stranger_"):
        known_people = [p for p in db.list_people() if p.get("person_type", "known") == "known"]
        owner = (
            sorted(known_people, key=lambda p: p["enrolled_at"])[0]["name"]
            if known_people else None
        )
        addendum = (
            "You are speaking with an unknown visitor — respond warmly and naturally. "
            "Learn their name organically; ask when the moment feels right. "
        )
        if owner:
            addendum += (
                f"If it feels natural, ask if they know {owner}. "
                f"If yes, explore how they know them and the relationship. "
            )
        addendum += "Do not share private information about enrolled persons."

    # Room context — mirrors pipeline.py lines 2900-2909
    if len(pipeline._active_sessions) > 1:
        parts = []
        for _rpid, _rsess in pipeline._active_sessions.items():
            label = "speaking" if _rpid == pid else "present"
            parts.append(f"{_rsess['person_name']} ({label})")
        room_line = "Room: " + ", ".join(parts)
        addendum = (room_line + "\n\n" + addendum) if addendum else room_line

    return addendum


# ═══════════════════════════════════════════════════════════════════════════════
# G4 stranger gate (mirrors pipeline.py run() loop lines 2858-2879)
# ═══════════════════════════════════════════════════════════════════════════════

def _check_stranger_gate(pid: str, text: str, db: FaceDB) -> bool:
    """
    Check G4 system-name gate for stranger sessions.

    Returns True  → proceed with conversation_turn()
    Returns False → gate is active and name not heard — skip this turn
    """
    sess = pipeline._active_sessions.get(pid, {})
    if not sess.get("waiting_for_name"):
        return True   # not waiting — proceed

    sys_name    = pipeline._active_system_name.lower()
    name_pattern = r"\b" + re.escape(sys_name) + r"\b"
    if re.search(name_pattern, text.lower()):
        # System name heard — unlock session
        pipeline._active_sessions[pid]["waiting_for_name"] = False
        print(f"[Sim] G4 gate cleared for {pid} — heard '{pipeline._active_system_name}'")
        # Progressive enrollment: create DB entry now
        if not pipeline._active_sessions[pid].get("db_enrolled"):
            db.add_stranger("visitor", person_id=pid)
            pipeline._active_sessions[pid]["db_enrolled"]     = True
            pipeline._active_sessions[pid]["confidence_tier"] = "enrolled_1"
            pipeline._conversation[pid] = []
            print(f"[Sim] Progressive enroll: DB entry created for {pid}")
        return True   # proceed
    else:
        print(f"[Sim] G4 gate active for {pid} — '{pipeline._active_system_name}' not heard, skipping")
        return False  # block


# ═══════════════════════════════════════════════════════════════════════════════
# Directive and turn execution
# ═══════════════════════════════════════════════════════════════════════════════

_TURN_RE = re.compile(r"^\[([A-Z][A-Z0-9_|]*)\]\s+(.+)$")


async def _handle_directive(
    directive: str,
    cast: dict,
    db: FaceDB,
    issues: list[str],
    pending_new_face: list[str],
) -> None:
    """Execute a single ---VERB ARGS directive line."""
    parts = directive[3:].split(maxsplit=1)   # strip leading ---
    verb  = parts[0].upper()
    args  = parts[1].strip() if len(parts) > 1 else ""

    if verb == "ENTER":
        handle = args.upper()
        if handle not in cast:
            raise ValueError(f"---ENTER: unknown handle '{handle}'")
        entry = cast[handle]
        _open_sim_session_for(entry, db)
        pending_new_face.append(handle)
        print(f"[Sim] {entry['person_name']} entered frame")

    elif verb == "LEAVE":
        handle = args.upper()
        if handle not in cast:
            raise ValueError(f"---LEAVE: unknown handle '{handle}'")
        cast[handle]["in_frame"] = False
        print(f"[Sim] {cast[handle]['person_name']} left frame")

    elif verb == "CLOSE":
        handle = args.upper()
        if handle not in cast:
            raise ValueError(f"---CLOSE: unknown handle '{handle}'")
        _close_sim_session_for(cast[handle])
        await asyncio.sleep(2.0)   # let brain drain session-end tasks

    elif verb == "CLOSE_ALL":
        for entry in list(cast.values()):
            if entry["session_open"]:
                _close_sim_session_for(entry)
        await asyncio.sleep(2.0)

    elif verb == "PAUSE":
        try:
            secs = float(args)
        except ValueError:
            secs = 1.0
        print(f"[Sim] Pausing {secs}s...")
        _heartbeat_in_frame_sessions(cast)
        await asyncio.sleep(secs)

    elif verb == "SILENCE":
        # Simulate no-speech event — DO NOT call conversation_turn
        # Updates _last_user_speech_at to age the KAIROS clock
        print("[Sim] Silence event — no speech")
        _heartbeat_in_frame_sessions(cast)

    elif verb == "ASSERT":
        _handle_assert(args, cast, issues)

    else:
        raise ValueError(f"Unknown directive verb: '{verb}'")


def _handle_assert(args: str, cast: dict, issues: list[str]) -> None:
    """Evaluate an inline ---ASSERT check. Appends failures to issues."""
    parts = args.split(maxsplit=1)
    check  = parts[0].upper()
    handle = parts[1].upper() if len(parts) > 1 else ""

    if handle and handle not in cast:
        issues.append(f"ASSERT {check}: unknown handle '{handle}'")
        return

    entry = cast.get(handle, {})
    pid   = entry.get("person_id") if entry else None
    sess  = pipeline._active_sessions.get(pid, {}) if pid else {}

    if check == "SESSION_OPEN":
        ok = pid in pipeline._active_sessions
        _print_assert(f"SESSION_OPEN {handle}", ok, issues)

    elif check == "SESSION_CLOSED":
        ok = pid not in pipeline._active_sessions
        _print_assert(f"SESSION_CLOSED {handle}", ok, issues)

    elif check == "WAITING_FOR_NAME":
        ok = sess.get("waiting_for_name", False) is True
        _print_assert(f"WAITING_FOR_NAME {handle}", ok, issues)

    elif check == "GATE_CLEARED":
        ok = not sess.get("waiting_for_name", False)
        _print_assert(f"GATE_CLEARED {handle}", ok, issues)

    else:
        issues.append(f"ASSERT: unknown check '{check}'")


def _print_assert(label: str, ok: bool, issues: list[str]) -> None:
    if ok:
        print(f"[Sim] ASSERT PASS: {label}")
    else:
        msg = f"ASSERT FAIL: {label}"
        print(f"[Sim] {msg}")
        issues.append(msg)


async def _execute_turn(
    event_type: str,
    payload: str,
    cast: dict,
    db: FaceDB,
    turn_num: int,
    issues: list[str],
    pending_new_face: list[str],
) -> None:
    """Execute one [HANDLE] or [HANDLE|HANDLE2] turn."""
    m = _TURN_RE.match(payload)
    if not m:
        issues.append(f"Turn {turn_num}: unparseable payload: {payload!r}")
        return

    handle_part = m.group(1).upper()
    text_part   = m.group(2).strip()

    if event_type == "multi":
        # Within-utterance diarization: [A|B] text_A | text_B
        handles = [h.strip().upper() for h in handle_part.split("|")]
        if len(handles) < 2:
            issues.append(f"Turn {turn_num}: multi turn needs at least 2 handles: {payload!r}")
            return
        # Split text at | — left = primary, right = secondary
        text_parts = [t.strip() for t in text_part.split("|", 1)]
        left_text  = text_parts[0]
        right_text = text_parts[1] if len(text_parts) > 1 else ""

        primary_handle   = handles[0]
        secondary_handle = handles[1]

        if primary_handle not in cast:
            issues.append(f"Turn {turn_num}: unknown handle '{primary_handle}'")
            return
        if secondary_handle not in cast:
            issues.append(f"Turn {turn_num}: unknown handle '{secondary_handle}'")
            return

        p_entry = cast[primary_handle]
        s_entry = cast[secondary_handle]
        p_pid   = p_entry["person_id"]
        p_name  = p_entry["person_name"]
        s_name  = s_entry["person_name"]

        # Build combined text mirroring pipeline.py diarization output (line 2676)
        combined_text = f"[{p_name}]: {left_text}\n[{s_name}]: {right_text}" if right_text else left_text

        _heartbeat_in_frame_sessions(cast)
        pipeline._last_user_speech_at = time.time()

        new_face_name = None
        if pending_new_face:
            h = pending_new_face.pop(0)
            new_face_name = cast[h]["person_name"]

        if not _check_stranger_gate(p_pid, combined_text, db):
            return

        vs = _build_vision_state(p_entry, new_face_name=new_face_name)
        vos = _build_voice_state(p_entry, voice_confidence=0.75)
        addendum = _build_addendum_override(p_pid, db)

        print(f"\n{'─' * 70}")
        print(f"[USER] Turn {turn_num} [diarized]: {combined_text[:120]}")
        print(f"{'─' * 70}")
        try:
            await conversation_turn(
                combined_text, p_pid, p_name, db,
                vision_state=vs,
                voice_state=vos,
                prompt_addendum_override=addendum,
            )
        except Exception as e:
            msg = f"Turn {turn_num} CRASHED (multi): {e}"
            print(f"[Sim] ERROR — {msg}")
            issues.append(msg)
            import traceback; traceback.print_exc()
            return

        # Sync name changes back (update_person_name tool may have fired)
        _sync_name_back(primary_handle, cast)
        return

    # ── Single-speaker turn ───────────────────────────────────────────────────
    handle = handle_part.upper()
    if handle not in cast:
        issues.append(f"Turn {turn_num}: unknown handle '{handle}'")
        return

    entry = cast[handle]
    pid   = entry["person_id"]
    name  = entry["person_name"]

    _heartbeat_in_frame_sessions(cast)
    pipeline._last_user_speech_at = time.time()

    new_face_name = None
    if pending_new_face:
        h = pending_new_face.pop(0)
        new_face_name = cast[h]["person_name"]

    if not _check_stranger_gate(pid, text_part, db):
        return

    vs      = _build_vision_state(entry, new_face_name=new_face_name)
    vos     = _build_voice_state(entry)
    addendum = _build_addendum_override(pid, db)

    print(f"\n{'─' * 70}")
    print(f"[USER] Turn {turn_num} [{handle}]: {text_part}")
    print(f"{'─' * 70}")
    try:
        await conversation_turn(
            text_part, pid, name, db,
            vision_state=vs,
            voice_state=vos,
            prompt_addendum_override=addendum,
        )
    except Exception as e:
        msg = f"Turn {turn_num} CRASHED: {e}"
        print(f"[Sim] ERROR — {msg}")
        issues.append(msg)
        import traceback; traceback.print_exc()
        return

    _sync_name_back(handle, cast)


def _sync_name_back(handle: str, cast: dict) -> None:
    """If update_person_name tool fired, reflect the new name in the cast entry."""
    entry = cast[handle]
    pid   = entry["person_id"]
    if pid in pipeline._active_sessions:
        live_name = pipeline._active_sessions[pid].get("person_name", entry["person_name"])
        if live_name != entry["person_name"]:
            print(f"[Sim] Name update: {entry['person_name']} → {live_name}")
            entry["person_name"] = live_name


# ═══════════════════════════════════════════════════════════════════════════════
# State persistence (v2 — multi-person aware)
# ═══════════════════════════════════════════════════════════════════════════════

def _save_session_state(turn_count: int, system_name: str, cast: dict | None = None) -> None:
    state: dict = {
        "v":           2,
        "turn_count":  turn_count,
        "system_name": system_name,
    }
    if cast:
        state["cast"] = {
            handle: {
                "person_id":   entry["person_id"],
                "person_name": entry["person_name"],
                "person_type": entry["person_type"],
                "in_frame":    entry["in_frame"],
            }
            for handle, entry in cast.items()
        }
    else:
        # Legacy
        state.update({
            "person_id":   _LEGACY_PERSON_ID,
            "person_name": _LEGACY_PERSON_NAME,
        })
    _STATE_FILE.write_text(json.dumps(state), encoding="utf-8")


def _load_session_state() -> dict | None:
    if _STATE_FILE.exists():
        try:
            data = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
            # Accept both v1 (no "v" key) and v2 state files
            return data
        except Exception:
            pass  # OPTIONAL: malformed state file — fall through to None
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# Pipeline initialization
# ═══════════════════════════════════════════════════════════════════════════════

async def initialize() -> FaceDB:
    """Initialize all pipeline infrastructure (camera/vision skipped)."""
    _wiring._shutdown_event    = asyncio.Event()
    pipeline._last_user_speech_at = time.time()
    pipeline._last_kairos_at      = time.time()

    db = FaceDB(db_path=str(SIM_DB_PATH), faiss_path=SIM_FAISS_PATH)
    print(f"[Sim] DB loaded from {SIM_FACES_DIR} (isolated — production DB untouched)")

    loaded_name = db.get_system_identity("system_name") or DEFAULT_SYSTEM_NAME
    if loaded_name.lower() in _INVALID_SYSTEM_NAMES:
        loaded_name = DEFAULT_SYSTEM_NAME
    pipeline._active_system_name = loaded_name
    pipeline._brain_orchestrator and pipeline._brain_orchestrator.set_system_name(loaded_name)
    print(f"[Sim] System name: {pipeline._active_system_name}")

    print("[Sim] Loading audio models...")
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, preload_models)
    print("[Sim] Audio models ready")

    await loop.run_in_executor(None, voice_mod.load_speaker_embedder)
    pipeline._voice_gallery.update(db.load_voice_profiles())
    print(f"[Sim] Voice gallery: {len(pipeline._voice_gallery)} person(s)")

    pipeline._emotion_agents = {}
    await loop.run_in_executor(None, EmotionAgent()._ensure_loaded)
    print("[Sim] Emotion model ready")

    _wiring._brain_orchestrator = BrainOrchestrator(
        _wiring._shutdown_event,
        brain_db_path=SIM_BRAIN_PATH,
        graph_db_path=SIM_GRAPH_PATH,
        faces_db_path=SIM_DB_PATH,
    )
    pipeline._brain_orchestrator.set_system_name(pipeline._active_system_name)
    asyncio.create_task(pipeline._brain_orchestrator.run())
    print("[Sim] Brain orchestrator running")

    pipeline._cloud_state = CloudState.ONLINE
    return db


# ═══════════════════════════════════════════════════════════════════════════════
# Legacy single-person session (backward compat)
# ═══════════════════════════════════════════════════════════════════════════════

def _open_legacy_session(db: FaceDB) -> None:
    """Open a known-person session for the legacy sim user."""
    db.add_person(_LEGACY_PERSON_ID, _LEGACY_PERSON_NAME, person_type="known")
    now = time.time()
    if _LEGACY_PERSON_ID not in pipeline._active_sessions:
        print(f"[Session] Open: {_LEGACY_PERSON_ID} (sim) — {_LEGACY_PERSON_NAME}")
        pipeline._active_sessions[_LEGACY_PERSON_ID] = {
            "person_id":          _LEGACY_PERSON_ID,
            "person_name":        _LEGACY_PERSON_NAME,
            "session_type":       "sim",
            "person_type":        "known",
            "waiting_for_name":   False,
            "last_face_seen":     now,
            "last_spoke_at":      now,
            "voice_confidence":   1.0,
            "started_at":         now,
            "kairos_clock_reset": True,
            "db_enrolled":        False,
        }
    if _LEGACY_PERSON_ID not in pipeline._conversation:
        pipeline._conversation[_LEGACY_PERSON_ID] = db.load_conversation_history(_LEGACY_PERSON_ID)


# ═══════════════════════════════════════════════════════════════════════════════
# Main entry points
# ═══════════════════════════════════════════════════════════════════════════════

async def run_turns(turns_file: str) -> None:
    """Initialize pipeline and run all events from turns_file."""
    db = await initialize()

    turns_path = pathlib.Path(turns_file)
    if not turns_path.exists():
        print(f"[Sim] ERROR: turns file not found: {turns_file}")
        return

    cast, events = _parse_turn_file(turns_path)
    is_multi = cast is not None

    # Load prior state
    prior       = _load_session_state()
    turn_offset = prior["turn_count"] if prior else 0
    if prior:
        print(f"[Sim] Resuming from turn {turn_offset} (loaded from session state)")

    if is_multi:
        # ── Multi-person mode ─────────────────────────────────────────────────
        # Pre-register all known persons in DB (INSERT OR IGNORE — safe)
        for entry in cast.values():
            if entry["person_type"] != "stranger":
                db.add_person(
                    entry["person_id"],
                    entry["person_name"],
                    person_type=entry["person_type"],
                )
        print(f"[Sim] Multi-person mode — {len(cast)} cast member(s): {', '.join(cast.keys())}")
    else:
        # ── Legacy single-person mode ─────────────────────────────────────────
        _open_legacy_session(db)
        print(f"[Sim] Legacy mode — session open for {_LEGACY_PERSON_NAME}")

    turn_events = [e for e in events if e[0] in ("turn", "multi", "legacy")]
    print(f"[Sim] {len(turn_events)} conversation turn(s) in {turns_path.name}")
    print(f"[Sim] {len(events) - len(turn_events)} directive/other event(s)")
    print("=" * 70)

    issues:          list[str] = []
    pending_new_face: list[str] = []
    turn_counter = 0

    for event_type, payload in events:
        if event_type == "directive":
            await _handle_directive(payload, cast, db, issues, pending_new_face)

        elif event_type in ("turn", "multi"):
            turn_counter += 1
            global_turn = turn_offset + turn_counter
            pipeline._last_user_speech_at = time.time()
            await _execute_turn(
                event_type, payload, cast, db,
                global_turn, issues, pending_new_face,
            )
            await asyncio.sleep(1.0)   # let brain agent start processing
            _save_session_state(global_turn, pipeline._active_system_name, cast)

        elif event_type == "legacy":
            turn_counter += 1
            global_turn = turn_offset + turn_counter
            print(f"\n{'─' * 70}")
            print(f"[USER] Turn {global_turn} ({turn_counter}/{len(turn_events)}): {payload}")
            print(f"{'─' * 70}")
            pipeline._last_user_speech_at = time.time()
            if _LEGACY_PERSON_ID in pipeline._active_sessions:
                pipeline._active_sessions[_LEGACY_PERSON_ID]["last_face_seen"] = time.time()
            try:
                await conversation_turn(payload, _LEGACY_PERSON_ID, _LEGACY_PERSON_NAME, db)
            except Exception as e:
                msg = f"Turn {global_turn} CRASHED: {e}"
                print(f"[Sim] ERROR — {msg}")
                issues.append(msg)
                import traceback; traceback.print_exc()
            await asyncio.sleep(1.0)
            _save_session_state(global_turn, pipeline._active_system_name)

    print(f"\n{'=' * 70}")
    print(f"[Sim] Batch complete — {turn_counter} turn(s) processed (offset {turn_offset})")
    print(f"[Sim] System name: {pipeline._active_system_name}")

    if issues:
        print(f"\n[Sim] ⚠  {len(issues)} issue(s):")
        for iss in issues:
            print(f"       • {iss}")
    else:
        print("[Sim] No issues detected")

    print("[Sim] Waiting for brain agent to drain...")
    await asyncio.sleep(8.0)
    _wiring._shutdown_event.set()
    print("[Sim] Done.")


async def close_session() -> None:
    """Close the sim session cleanly (triggers session-end tasks)."""
    db = await initialize()
    _open_legacy_session(db)
    if pipeline._brain_orchestrator:
        print(f"[Sim] Running session-end tasks for {_LEGACY_PERSON_NAME}...")
        pipeline._brain_orchestrator.notify_session_end(_LEGACY_PERSON_ID)
        await asyncio.sleep(5.0)
    _wiring._shutdown_event.set()
    _STATE_FILE.unlink(missing_ok=True)
    print("[Sim] Session closed and state cleared.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="dog-ai headless conversation simulator")
    parser.add_argument("turns_file", nargs="?", help="Path to turns .txt file")
    parser.add_argument("--close-session", action="store_true", help="Close sim session cleanly")
    args = parser.parse_args()

    if args.close_session:
        asyncio.run(close_session())
    elif args.turns_file:
        asyncio.run(run_turns(args.turns_file))
    else:
        parser.print_help()
