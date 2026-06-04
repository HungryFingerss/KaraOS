"""#5 Slice D — Layer-1 behavioral tests for the VoiceEvidence-timestamp read fabric (§1.4/§3.D).

The §1.4 regression: Slices A/B flipped the `update_face_seen(ts=)` / `update_voice_heard(ts=)`
writer args to time.monotonic() (those args ALSO write the VoiceEvidence timestamps
face_last_seen_ts / voice_last_heard_ts via dataclasses.replace), but the READERS stayed wall —
so `face_age = wall_now - mono_field ≈ +1.78e9 > MAX_AGE` → Path-A face-witness never fired, and
the brain IDENTITY EVIDENCE `_face_age`/`_voice_age` were garbage. Slice D flips the two readers
to monotonic (pipeline.py `_voice_accum_allowed` + core/brain.py IDENTITY EVIDENCE block).

Why a BEHAVIORAL backstop on top of the §3.D.2 detector strengthening (per §3.D PI-2): the paired
detector is structurally blind to this fabric (dataclasses.replace write + dict/aliased read), and
`voice_last_heard_ts` has NO other reader — its ONLY production reader is the brain `_voice_age`
display, so without this test its single structural guard is the §3.D.2 self-test alone. These
replicated-decision helpers (à la Slice B's #22 `_holder_visible_for_extension`) hold the field at a
recent MONOTONIC value (matching the now-monotonic writer) and prove the read is CORRECT under a
monotonic `now` and BROKEN under a wall `now` — the exact pre-Slice-D bug, net-zero on revert.

Direction note: the field is monotonic (small, seconds-since-boot). A wall `now` (~1.78e9) minus a
monotonic field is ≈ +1.78e9, which blows past every MAX_AGE gate → recent evidence reads as ancient
→ the face-witness path dies / the displayed age is garbage. (Same wall≫monotonic assumption the
Slice-B tests rely on; monotonic never approaches the wall epoch on any real uptime.)

Spec: tests/presence_fabric_clock_migration_spec.md §1.4 / §3.D / §3.D.2 PI-1+PI-2.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import time

import pytest

from core.config import (
    VOICE_ACCUM_FACE_WITNESS_MIN_CONF,
    VOICE_ACCUM_FACE_WITNESS_MAX_AGE_SEC,
    VOICE_ACCUM_VOICE_SELF_MATCH_MIN,
    VOICE_ACCUM_MATURE_SAMPLE_COUNT,
)


# ── Replicated production-decision helpers (the #22 fail-on-revert pattern) ───────────────

def _path_a_face_witness_fires(*, face_match_conf: float, anti_spoof_live: bool,
                               face_last_seen_ts: float, now: float) -> bool:
    """Replicates pipeline.py `_voice_accum_allowed` Path A:
        face_age = now - face_last_seen_ts
        fires iff conf >= MIN_CONF and anti_spoof_live and face_age <= MAX_AGE_SEC."""
    face_age = now - face_last_seen_ts
    return (face_match_conf >= VOICE_ACCUM_FACE_WITNESS_MIN_CONF
            and anti_spoof_live
            and face_age <= VOICE_ACCUM_FACE_WITNESS_MAX_AGE_SEC)


def _brain_face_ok(*, face_match_conf: float, anti_spoof_live: bool,
                   face_last_seen_ts: float, now: float) -> bool:
    """Replicates core/brain.py IDENTITY EVIDENCE `_face_ok` (the face channel verdict):
        _face_age = now - face_last_seen_ts  (if face_last_seen_ts else None)
        _face_ok  = conf >= MIN and live and _face_age is not None and _face_age <= MAX_AGE."""
    _face_age = (now - face_last_seen_ts) if face_last_seen_ts else None
    return (face_match_conf >= VOICE_ACCUM_FACE_WITNESS_MIN_CONF and anti_spoof_live
            and _face_age is not None and _face_age <= VOICE_ACCUM_FACE_WITNESS_MAX_AGE_SEC)


def _brain_voice_age(*, voice_last_heard_ts: float, now: float):
    """Replicates core/brain.py:2723 `_voice_age = now - voice_last_heard_ts` (the display read).
    This is the ONLY production reader of voice_last_heard_ts — §3.D.2 + this test are its sole guards."""
    return (now - voice_last_heard_ts) if voice_last_heard_ts else None


# ── Path A face-witness — REAL `_voice_accum_allowed` drive ───────────────────────────────

@pytest.mark.asyncio
async def test_path_a_face_witness_fires_under_monotonic_face_write():
    """Drive the REAL SessionStore + `_voice_accum_allowed`: a session whose face_last_seen_ts was
    written via the REAL update_face_seen with a recent MONOTONIC clock fires Path A — because the
    Slice-D reader flip (`now = time.monotonic()`) now matches the monotonic write.

    Net-zero fail-on-revert (demonstrated at the §8 gate): revert pipeline.py `_voice_accum_allowed`
    `now` to time.time() → face_age = wall_now − mono_field ≈ +1.78e9 > MAX_AGE → path 'refused' →
    this assertion goes RED for the production reason."""
    import pipeline as _pl
    pid = "va_path_a_consistent"
    await _pl._session_store.open_session(
        pid, "Faye", "stranger", "voice", now=time.time(), now_mono=time.monotonic())
    await _pl._session_store.update_face_seen(
        pid, conf=max(0.9, VOICE_ACCUM_FACE_WITNESS_MIN_CONF + 0.1),
        ts=time.monotonic(), anti_spoof_live=True, anti_spoof_score=0.95)
    allowed, reason, path = _pl._voice_accum_allowed(pid)
    assert allowed and path == "face_witness", (
        "a recent monotonic-written face_last_seen_ts must fire Path A face-witness under the "
        f"Slice-D monotonic reader; got allowed={allowed}, path={path!r}, reason={reason!r}"
    )


def test_path_a_face_witness_decision_correct_under_monotonic_dead_under_wall():
    """Replicated Path-A decision: with face_last_seen_ts held at a recent MONOTONIC value, the
    decision FIRES under a monotonic `now` and is DEAD under a wall `now` (wall_now − mono_field
    ≈ +1.78e9 > MAX_AGE). This is the exact §1.4 bug + the Slice-D fix, in one assertion pair."""
    face_ts = time.monotonic() - 2.0  # seen ~2s ago, monotonic (matches the now-monotonic writer)
    assert _path_a_face_witness_fires(
        face_match_conf=0.9, anti_spoof_live=True, face_last_seen_ts=face_ts,
        now=time.monotonic()) is True, "monotonic read of a recent monotonic face must fire Path A"
    assert _path_a_face_witness_fires(
        face_match_conf=0.9, anti_spoof_live=True, face_last_seen_ts=face_ts,
        now=time.time()) is False, (
        "WALL read of a monotonic face_last_seen_ts (the pre-Slice-D bug) makes face_age ≈ +1.78e9 "
        "> MAX_AGE → Path A dead; if this flips, the reader stopped mis-reading and the fix is moot"
    )


# ── brain IDENTITY EVIDENCE — _face_age verdict (PI-2 asymmetry closure) ──────────────────

def test_brain_face_ok_correct_under_monotonic_dead_under_wall():
    """Replicated brain `_face_ok` verdict (face channel): recent MONOTONIC face_last_seen_ts →
    True under monotonic `now`, False under wall `now`. Closes the §3.D PI-2 asymmetry: the brain
    face-channel read gets a behavioral backstop, not just the §3.D.2 structural detector."""
    face_ts = time.monotonic() - 2.0
    assert _brain_face_ok(
        face_match_conf=0.9, anti_spoof_live=True, face_last_seen_ts=face_ts,
        now=time.monotonic()) is True, "monotonic read → recent face → high-confidence face channel"
    assert _brain_face_ok(
        face_match_conf=0.9, anti_spoof_live=True, face_last_seen_ts=face_ts,
        now=time.time()) is False, (
        "WALL read of a monotonic face_last_seen_ts pins the brain face channel to 'weak/missing' "
        "(_face_age ≈ +1.78e9 > MAX_AGE); the Slice-D brain.py:2716 monotonic flip fixes it"
    )


# ── brain IDENTITY EVIDENCE — _voice_age display (voice_last_heard_ts sole-reader backstop) ──

def test_brain_voice_age_sane_under_monotonic_garbage_under_wall():
    """voice_last_heard_ts has NO other production reader than this brain `_voice_age` display, so
    §3.D.2 + this test are its ONLY guards (the architect's PI-2 reason for a behavioral backstop).
    A recent MONOTONIC voice_last_heard_ts gives a sane "Xs ago" under monotonic `now` and absurd
    garbage (~1.78e9s) under wall `now`."""
    voice_ts = time.monotonic() - 2.0
    age_mono = _brain_voice_age(voice_last_heard_ts=voice_ts, now=time.monotonic())
    assert age_mono is not None and 0.0 <= age_mono < 60.0, (
        f"monotonic read of a recent monotonic voice_last_heard_ts must be a sane elapsed age, got {age_mono}"
    )
    age_wall = _brain_voice_age(voice_last_heard_ts=voice_ts, now=time.time())
    assert age_wall is not None and age_wall > 1e8, (
        "WALL read of a monotonic voice_last_heard_ts (pre-Slice-D) yields ~1.78e9s — an absurd "
        f"'heard 1780000000s ago' display; got {age_wall}. The brain.py:2716 monotonic flip fixes it"
    )


# ── REAL-DRIVE of _build_system_prompt — golden-test-first production-driven RED-on-revert ──

def test_build_system_prompt_identity_evidence_sane_ages_under_monotonic():
    """Golden-test-first real-drive of the brain reads (Layer-3 addendum). Demo 3 proved the
    DETECTOR catches brain.py:2723/2728 on revert and the replicated helpers document the decision,
    but neither drove the REAL _build_system_prompt. This does: it renders the actual <<<IDENTITY
    EVIDENCE>>> block from an identity_evidence whose face_last_seen_ts + voice_last_heard_ts are
    recent time.monotonic() values, and asserts sane "seen/heard <60s ago" ages + a high-confidence
    verdict.

    Production-driven fail-on-revert: revert brain.py `_now` mono->wall and _face_age/_voice_age
    become ≈ +1.78e9 -> the rendered ages blow past 60s AND _face_ok flips False (age > MAX_AGE) so
    the verdict downgrades off 'high-confidence' -> BOTH assertions go RED for the production reason.
    """
    import re
    from core.brain import _build_system_prompt
    now_mono = time.monotonic()
    vision_state = {
        "identity_evidence": {
            # Cross the thresholds regardless of exact config values.
            "face_match_conf": max(0.90, VOICE_ACCUM_FACE_WITNESS_MIN_CONF),
            "face_last_seen_ts": now_mono,            # recent MONOTONIC (matches the now-mono writer)
            "anti_spoof_live": True,
            "anti_spoof_score": 0.95,
            "voice_match_conf": max(0.70, VOICE_ACCUM_VOICE_SELF_MATCH_MIN),
            "voice_sample_count": max(10, VOICE_ACCUM_MATURE_SAMPLE_COUNT),
            "voice_last_heard_ts": now_mono,          # recent MONOTONIC
        }
    }
    prompt = _build_system_prompt("Jagan", vision_state=vision_state, system_name="Kara")
    assert "<<<IDENTITY EVIDENCE>>>" in prompt, "IDENTITY EVIDENCE block must render"
    _block = prompt[prompt.find("<<<IDENTITY EVIDENCE>>>"):]
    _face_m = re.search(r"seen (\d+(?:\.\d+)?)s ago", prompt)
    _voice_m = re.search(r"heard (\d+(?:\.\d+)?)s ago", prompt)
    assert _face_m is not None and float(_face_m.group(1)) < 60.0, (
        f"face age must be a sane recent elapsed (<60s) under the monotonic read; block:\n{_block}"
    )
    assert _voice_m is not None and float(_voice_m.group(1)) < 60.0, (
        f"voice age must be a sane recent elapsed (<60s) under the monotonic read; block:\n{_block}"
    )
    assert "verdict: high-confidence identity" in prompt, (
        "a recent monotonic face (conf>=MIN, live, age<=MAX_AGE) + mature voice must yield a "
        f"high-confidence verdict; reverting brain.py _now mono->wall downgrades it. block:\n{_block}"
    )
