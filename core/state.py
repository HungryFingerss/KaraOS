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
    """Set a field that survives every subsequent write() call."""
    _persistent[key] = value


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
