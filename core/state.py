"""
core/state.py — Shared state between pipeline and dashboard
Pipeline writes → dashboard reads via /api/status
"""
import json
import os
import tempfile
import time
from typing import Optional
from core.config import STATE_FILE


_persistent: dict = {}  # fields merged into every write() — set once at startup


def set_persistent(key: str, value) -> None:
    """Set a field that survives every subsequent write() call.

    Atomic-replace pattern: rebinds `_persistent` to a new dict rather
    than mutating in place. CPython STORE_NAME is GIL-atomic, so a
    concurrent reader iterating the OLD dict reference sees a
    consistent snapshot.

    NOTE: This protects readers from torn iteration. It does NOT protect
    against concurrent writers losing updates (RMW race — multiple
    writers can both load the old dict, both build new dicts, and the
    second STORE wins). Production has 1 writer at startup, so RMW is
    not a concern. If runtime writers are added, add `threading.Lock`.
    """
    global _persistent
    _persistent = {**_persistent, key: value}


def write(
    status: str = "idle",
    current_person: Optional[str] = None,
    current_person_id: Optional[str] = None,
    visible_people: list = None,
    mode: str = "watching",     # watching | listening | speaking | enrolling
    message: str = ""
):
    """Write current pipeline state to state file."""
    state = {
        "status":            status,
        "current_person":    current_person,
        "current_person_id": current_person_id,
        "visible_people":    visible_people or [],
        "mode":              mode,
        "message":           message,
        "updated_at":        time.time(),
        "online":            True,
        **_persistent,
    }
    # M8: atomic write — write to a sibling temp file then rename so the
    # dashboard never reads a half-written JSON if the pipeline crashes mid-write.
    try:
        fd, tmp_path = tempfile.mkstemp(
            dir=STATE_FILE.parent, prefix=".state_", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(state, f)
            os.replace(tmp_path, str(STATE_FILE))
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except Exception as e:
        print(f"[State] WARNING: failed to write state file: {e}")

    # P0.0.7 H9 — emit state_write event AFTER successful atomic-replace
    # (and after any logged-and-swallowed failure) via safe_emit_sync.
    # Single P0.4-annotated except lives inside safe_emit_sync.
    from core.event_log import safe_emit_sync, StateWritePayload
    safe_emit_sync(
        "state_write",
        StateWritePayload(
            mode=mode,
            current_person=current_person,
            current_person_id=current_person_id,
            visible_people=tuple(visible_people or ()),
            message=message,
        ),
        session_id=current_person_id,
    )


def read() -> dict:
    """Read current pipeline state."""
    try:
        if STATE_FILE.exists():
            data = json.loads(STATE_FILE.read_text())
            # If pipeline hasn't written in 10 seconds, mark offline
            if time.time() - data.get("updated_at", 0) > 10:
                data["online"] = False
            return data
    except Exception:
        pass  # OPTIONAL: state-file absent or corrupt — caller gets offline default
    return {"online": False, "mode": "offline", "status": "offline"}
