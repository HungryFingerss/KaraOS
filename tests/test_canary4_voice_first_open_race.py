"""Canary #4 (2026-05-31) golden tests — voice-first session-open race.

Camera off, Jagan spoke: got no answer (symptom A), then got assigned to a visitor
(symptom B). Root cause: _open_session registered the session via a fire-and-forget
create_task, so it was NOT synchronously visible — the very next re-check
(`if not _session_store.peek_all_snapshots()` at pipeline.py:7684) ran the stranger
engagement gate even after a known speaker was identified+opened. Fix B1: synchronous
session visibility via SessionStore._sync_open_session (the first blessed sync write).

Golden-test-first (RED before the fix):
  GT0   — _open_session is synchronously visible (RED today: create_task → peek races).
  GT-A  — known speaker by voice, no face, NO system name → don't engage stranger.
  GT-B  — known speaker by voice, no face, WITH system name → still don't engage (the
          known session is opened, the gate is skipped — name is irrelevant).
GT-A/GT-B target the Q2 decision helper _voice_first_should_engage_stranger (RED today:
the helper doesn't exist).
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import pytest


# ── GT0 — synchronous session visibility (the root-cause assertion) ───────────


@pytest.mark.asyncio
async def test_gt0_open_session_is_synchronously_visible():
    """GT0: after `_open_session(...)` returns, `peek_snapshot(pid)` must be non-None
    SYNCHRONOUSLY — no await/drain between the open and the peek.

    RED today: _open_session fires `create_task(_session_store.open_session(...))`; with
    no await before the peek the task hasn't drained → peek is None → the voice-first
    re-check runs the stranger gate. GREEN after B1 (direct _sync_open_session).

    PI-3: set up a returning (cached-history) speaker — the deterministic-race shape (the
    voice-first flow's `await ensure_history_loaded` is a no-yield cache hit for such a
    speaker, so the open task never drained before :7684 peeked)."""
    import pipeline as _pl

    pid = "jagan_x"
    _pl._session_store._sessions.pop(pid, None)
    await _pl._conversation_store.pop_history(pid)
    # Returning speaker: cached history → ensure_history_loaded would be a no-yield hit.
    await _pl._conversation_store.set_history(
        pid, [{"role": "user", "content": "hi", "ts": 0.0}]
    )

    _pl._open_session(pid, "Jagan", "voice", person_type="known")
    # NO await between the open and the peek — the session MUST be visible immediately.
    snap = _pl._session_store.peek_snapshot(pid)
    try:
        assert snap is not None, (
            "Canary #4 race: _open_session must register the session SYNCHRONOUSLY. "
            "Fire-and-forget create_task left it invisible to the very next "
            "peek_all_snapshots() re-check (pipeline.py:7684), so the stranger "
            "engagement gate ran even for an identified known speaker."
        )
        assert snap.person_type == "known"
        assert snap.person_name == "Jagan"
    finally:
        _pl._close_session(pid)


# ── GT-A / GT-B — the Q2 decision helper (camera-off, known speaker) ──────────


def test_gt_a_known_voice_no_name_does_not_engage_stranger():
    """GT-A: camera off, known speaker by voice, NO system name in the utterance →
    `_voice_first_should_engage_stranger` returns False. A known speaker opened a session
    (B1: synchronously visible) → the engagement gate is skipped → the turn is NOT dropped
    and NO stranger_visitor_* is opened. RED today: the helper doesn't exist."""
    import pipeline as _pl

    engage = _pl._voice_first_should_engage_stranger(
        voice_id_result="jagan_39194f",   # voice ID established a known speaker
        face_available=False,              # camera off — no face
        ambient_text="I think Lexi is taking time with the new grinder",  # no system name
        system_name="Kara",
    )
    assert engage is False, (
        "known speaker identified by voice → no stranger engagement, the gate is skipped "
        "(symptom A was the gate clearing _ambient_text and dropping the turn)"
    )


def test_gt_b_known_voice_with_name_does_not_engage_stranger():
    """GT-B: same camera-off known speaker but the utterance CONTAINS the system name →
    still returns False. The known session is opened, so the gate is skipped entirely —
    the system name is irrelevant once a known speaker is established (symptom B was the
    name passing the gate and opening a phantom visitor). RED today: helper missing."""
    import pipeline as _pl

    engage = _pl._voice_first_should_engage_stranger(
        voice_id_result="jagan_39194f",
        face_available=False,
        ambient_text="Shut down now Kara, Lexi will talk to you later",  # contains "Kara"
        system_name="Kara",
    )
    assert engage is False, (
        "a known speaker matched by voice must NOT spawn a phantom visitor even when the "
        "system name is present — the gate is skipped for an established known session"
    )


def test_gt_helper_engages_only_genuine_voice_only_stranger():
    """Contract companion (symmetric verification): the helper returns True ONLY for the
    genuine voice-only-stranger case — NO known voice match, NO face, AND the system name
    present. Proves B1's decision doesn't over- or under-engage. RED today: helper missing."""
    import pipeline as _pl

    # No known identity + name present → engage (genuine voice-only stranger).
    assert _pl._voice_first_should_engage_stranger(
        voice_id_result=None, face_available=False,
        ambient_text="Hey Kara", system_name="Kara",
    ) is True
    # No known identity + NO name → do not engage (drop / stay silent).
    assert _pl._voice_first_should_engage_stranger(
        voice_id_result=None, face_available=False,
        ambient_text="just talking to myself", system_name="Kara",
    ) is False
    # Camera fallback recognized a known face → known session → no stranger even with name.
    assert _pl._voice_first_should_engage_stranger(
        voice_id_result=None, face_available=True,
        ambient_text="Hey Kara", system_name="Kara",
    ) is False
