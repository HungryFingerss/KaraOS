# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors
"""100% line coverage for core.state — the pipeline↔dashboard IPC state file.

Part of the coverage-to-100 campaign (see COVERAGE.md). Fills the two gaps a
full-suite run left uncovered:

  * lines 86-87 — the inner ``except OSError: pass`` inside write()'s
    atomic-write cleanup. Reached only when the atomic write raises AND the
    tmp-file ``os.unlink`` cleanup ITSELF raises OSError (the "cleanup of a
    failed write also failed" sub-case).
  * lines 111-121 — the whole ``read()`` function: fresh state, stale state
    (>10s → online=False), missing file, and corrupt-JSON fallback.

All tests run headless: no GPU, camera, network, or real model downloads.
STATE_FILE is redirected to a pytest tmp_path and _persistent is reset per
test, mirroring tests/test_state_race.py.
"""

from __future__ import annotations

import json
import time

import pytest

from core import state as _state_mod


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    """Reset module globals between tests: empty _persistent + STATE_FILE
    pointed at a fresh tmp path so nothing touches the live faces/state.json.
    Each test's tmp path starts with NO state.json (the file-absent case gets
    it for free)."""
    monkeypatch.setattr(_state_mod, "_persistent", {})
    monkeypatch.setattr(_state_mod, "STATE_FILE", tmp_path / "state.json")
    yield


# ---------------------------------------------------------------------------
# read() — lines 111-121
# ---------------------------------------------------------------------------

def test_read_returns_fresh_state_and_leaves_online_untouched():
    """Fresh updated_at (< 10s ago): line 116 branch is False, so the online
    flag written to the file is preserved and the data dict is returned as-is
    (lines 111, 112-True, 113, 116-False, 118)."""
    sf = _state_mod.STATE_FILE
    sf.write_text(json.dumps({
        "status": "speaking",
        "mode": "listening",
        "current_person": "Jagan",
        "online": True,
        "updated_at": time.time(),
    }))

    out = _state_mod.read()

    assert out["status"] == "speaking"
    assert out["mode"] == "listening"
    assert out["current_person"] == "Jagan"
    # Fresh → the stale-flip at line 117 must NOT fire.
    assert out["online"] is True


def test_read_marks_stale_state_offline():
    """updated_at older than 10s: line 116 branch is True → line 117 flips
    online to False. Other fields survive; the mutated dict is returned."""
    sf = _state_mod.STATE_FILE
    sf.write_text(json.dumps({
        "status": "idle",
        "mode": "watching",
        "online": True,
        "updated_at": time.time() - 999.0,  # far past the 10s staleness gate
    }))

    out = _state_mod.read()

    assert out["online"] is False       # line 117 fired
    assert out["status"] == "idle"      # rest of the payload preserved
    assert out["mode"] == "watching"


def test_read_missing_updated_at_treated_as_stale():
    """No updated_at key → data.get('updated_at', 0) yields 0, so
    time.time() - 0 is a huge positive number > 10 → stale → online=False
    (line 116-True, 117). Guards the .get() default fallback."""
    sf = _state_mod.STATE_FILE
    sf.write_text(json.dumps({"status": "idle", "online": True}))

    out = _state_mod.read()

    assert out["online"] is False


def test_read_returns_offline_default_when_file_absent():
    """STATE_FILE.exists() is False (line 112 branch not taken) → falls
    straight through to the offline default at line 121."""
    sf = _state_mod.STATE_FILE
    assert not sf.exists()

    out = _state_mod.read()

    assert out == {"online": False, "mode": "offline", "status": "offline"}


def test_read_returns_offline_default_on_corrupt_json():
    """File exists but holds invalid JSON: json.loads raises inside the try
    (line 113) → except at line 119 swallows (line 120) → offline default
    at line 121."""
    sf = _state_mod.STATE_FILE
    sf.write_text("{ not valid json ]")

    out = _state_mod.read()

    assert out == {"online": False, "mode": "offline", "status": "offline"}


# ---------------------------------------------------------------------------
# write() atomic-cleanup OSError swallow — lines 86-87
# ---------------------------------------------------------------------------

def test_write_swallows_unlink_oserror_during_failed_write_cleanup(monkeypatch):
    """The 'cleanup of a failed atomic write also fails' path.

    json.dump is forced to raise (line 81), which enters the inner except at
    line 83. The tmp-file os.unlink cleanup (line 85) is forced to raise
    OSError, exercising the inner ``except OSError: pass`` at lines 86-87.
    The original error is then re-raised (line 88), caught by the outer
    except (line 89), and logged (line 90) — so write() must NOT propagate.

    safe_emit_sync is neutralized so the patched json.dump can't bleed into
    the event-log emit; the event-log path is out of scope for this test.
    """
    import core.event_log as _el
    monkeypatch.setattr(_el, "safe_emit_sync", lambda *a, **k: None)

    def _boom_dump(*_a, **_k):
        raise RuntimeError("json.dump exploded mid-write")

    def _boom_unlink(*_a, **_k):
        raise OSError("cannot unlink the temp file")

    monkeypatch.setattr(_state_mod.json, "dump", _boom_dump)
    monkeypatch.setattr(_state_mod.os, "unlink", _boom_unlink)

    # Must return normally: the OSError from unlink is swallowed (86-87) and
    # the re-raised write error is caught + logged by the outer handler.
    _state_mod.write(status="speaking", message="regression probe")


# ---------------------------------------------------------------------------
# write() happy path — makes this file a standalone coverage guarantee for
# core.state (set_persistent merge + the visible_people default branch).
# ---------------------------------------------------------------------------

def test_write_happy_path_writes_valid_json_with_persistent_merge():
    """Real atomic write to the tmp STATE_FILE. Confirms set_persistent()
    fields are merged into every write() and the file round-trips to valid
    JSON with the expected shape."""
    _state_mod.set_persistent("anti_spoof_enabled", True)

    _state_mod.write(
        status="speaking",
        current_person="Jagan",
        current_person_id="jagan_001",
        visible_people=["Jagan", "Lexi"],
        mode="listening",
        message="hello",
    )

    data = json.loads(_state_mod.STATE_FILE.read_text())
    assert data["status"] == "speaking"
    assert data["current_person"] == "Jagan"
    assert data["current_person_id"] == "jagan_001"
    assert data["visible_people"] == ["Jagan", "Lexi"]
    assert data["message"] == "hello"
    assert data["online"] is True
    assert "updated_at" in data
    # Persistent field survives into the written state.
    assert data["anti_spoof_enabled"] is True


def test_write_defaults_empty_visible_people():
    """write() with all defaults: `visible_people or []` yields [] and the
    default status/mode land in the file (visible_people None-default branch,
    line 65)."""
    _state_mod.write()

    data = json.loads(_state_mod.STATE_FILE.read_text())
    assert data["visible_people"] == []
    assert data["status"] == "idle"
    assert data["mode"] == "watching"
    assert data["current_person"] is None
