"""Canary #3 (2026-05-30 Jagan→Lexi) golden tests — written RED first.

Two coupled bugs, one canary:
  Part A — voice.embed returns None every call because the ECAPA subprocess loader
    (heavy_worker._get_subprocess_ecapa) calls from_hparams WITHOUT the hf_hub_download
    compatibility patch the main loader applies → empty gallery forever.
  Part B — the enrollment-mishear gate renamed a 55-turn best_friend (voice_n=0 from
    Part A + age<10min both incidentally true) → Jagan→Lexi corruption.

Golden-test-first (2026-05-30 directive): these are RED against current code (reproduce
the canary), then Part A/B turn them GREEN. They become the permanent regression guard.

  GT1   — real subprocess voice.embed → 192-dim, not None.  [CUDA/model-gated]
  GT1b  — _accumulate_voice grows voice_embedding_count by 1. [CUDA/model-gated]
  GT2   — 50-turn best_friend voice-only name claim → gate False + NO rename.
  GT2-companion (PI-1) — turn-1 fresh best_friend → gate True (B1 doesn't over-restrict).
  Q2-unit — _get_subprocess_ecapa routes through the shared patch helper. [always-CI]
  A2-guard — every SpeechBrain from_hparams is reached only through the shared patch
             helper (bidirectional inverse-check). [always-CI — the guard that would have
             gone RED the day P0.R6.Y landed].
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import ast
import inspect
import time as _t
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _require_real_ecapa_or_skip():
    """Gate GT1/GT1b on the real SpeechBrain model + CUDA (like the P0.R5 anchors).

    A vacuous skip on GPU-less CI is the same blindness that hid this bug for a week —
    so on the CUDA dev box / canary host this MUST actually run (RED before Part A)."""
    pytest.importorskip("speechbrain")
    try:
        import torch
    except Exception:
        pytest.skip("torch unavailable")
    if not torch.cuda.is_available():
        pytest.skip("CUDA unavailable — GT1/GT1b run on the CUDA dev box / canary host")


@pytest.fixture
def real_voice():
    """Swap the conftest `core.voice` STUB for the REAL module for the duration of one
    test (function-scoped, Q4).

    Why this fixture exists: the autouse `_reset_session_state_between_tests` fixture
    installs a `core.voice` stub whose `embed = AsyncMock(return_value=None)`. GT1/GT1b
    against that stub are vacuous — they test a mock hardcoded to return None (permanent
    false-RED; no host could ever pass them). This fixture pops the stub, imports the real
    `core.voice`, and — load-bearing — re-points `pipeline.voice_mod` to it (GT1b reaches
    embed through the `pipeline.py: from core import voice as voice_mod` alias, a SEPARATE
    binding from sys.modules["core.voice"], so re-importing the module alone is NOT enough).

    PI-1 hardening: try/finally restores the stub + the alias even if setup raises (so a
    setup-time assert can't leak the popped stub into sibling tests). Q3: the
    `_load_ecapa_patched` assert is MANDATORY + fail-loud — it guards against silently
    re-introducing the exact vacuity (real module never actually loaded)."""
    _require_real_ecapa_or_skip()  # Q2: the single call site for the gate
    import sys
    import importlib
    import pipeline

    _stub = sys.modules.get("core.voice")        # capture the stub BEFORE any mutation
    _orig_vm = getattr(pipeline, "voice_mod", None)
    try:
        sys.modules.pop("core.voice", None)
        real = importlib.import_module("core.voice")
        assert hasattr(real, "_load_ecapa_patched"), \
            "real core.voice not loaded — stub still active (fixture vacuity guard, Q3)"
        pipeline.voice_mod = real                # load-bearing: GT1b reaches embed via this alias
        yield real
    finally:                                     # PI-1: always restores, even on setup raise
        pipeline.voice_mod = _orig_vm
        if _stub is not None:
            sys.modules["core.voice"] = _stub
        else:
            sys.modules.pop("core.voice", None)


# ── GT1 — the ECAPA subprocess actually returns an embedding ──────────────────


@pytest.mark.asyncio
async def test_gt1_ecapa_subprocess_returns_embedding(real_voice):
    """GT1: the REAL subprocess voice.embed path returns a 192-dim embedding, not None.
    RED before Part A (subprocess load fails on the missing hf_hub_download patch)."""
    import numpy as np

    # 2.0s of mono float32 noise at 16 kHz — clears the 1.5s minimum length gate.
    rng = np.random.default_rng(0)
    audio = rng.standard_normal(32000).astype(np.float32) * 0.05

    emb = await real_voice.embed(audio, sample_rate=16000)
    assert emb is not None, "voice.embed returned None — ECAPA subprocess load failed"
    assert emb.shape == (192,), f"expected 192-dim ECAPA embedding, got {emb.shape}"


# ── GT1b — accumulation grows the gallery end-to-end ──────────────────────────


@pytest.mark.asyncio
async def test_gt1b_accumulate_voice_grows_gallery(real_voice, tmp_path):
    """GT1b: _accumulate_voice with a face-witnessed session + real ≥1.5s audio grows
    voice_embedding_count by 1 ([Voice] Profile updated, not embed returned None).
    RED before Part A, GREEN after. The `real_voice` fixture re-points pipeline.voice_mod
    to the real module so _accumulate_voice reaches the real embed (not the stub's None)."""
    import numpy as np
    from core.db import FaceDB
    import pipeline as _pl

    db = FaceDB(str(tmp_path / "faces.db"), faiss_path=str(tmp_path / "faiss.index"))
    pid = "stranger_gt1b"
    db.add_stranger("visitor", person_id=pid)

    rng = np.random.default_rng(1)
    audio = rng.standard_normal(32000).astype(np.float32) * 0.05  # 2.0s

    await _pl._voice_gallery_store.pop_gallery(pid)
    _pl._session_store._sessions.pop(pid, None)
    _pl._open_session(pid, "visitor", "voice",
                      person_type="stranger", engagement_gate_passed=True)
    await _pl._session_store.open_session(pid, "visitor", "stranger", "voice",
                                          now=_t.time(),
                                          bootstrap_credits=_pl.N_INITIAL_VOICE_BOOTSTRAP)
    before = db.voice_embedding_count(pid)
    try:
        await _pl._accumulate_voice(pid, audio, db, face_verified=True)
        after = db.voice_embedding_count(pid)
        assert after == before + 1, (
            f"voice_embedding_count must grow by 1 (real embed); before={before} after={after}"
        )
    finally:
        _pl._close_session(pid)
        db._conn.close()


# ── GT2 — a voice-only name claim does NOT rename an established best_friend ───


@pytest.mark.asyncio
async def test_gt2_established_best_friend_not_enrollment_mishear_candidate():
    """GT2 (gate): a 50-turn best_friend session (fresh within grace, voice_n=0) is NOT an
    enrollment-mishear candidate — the rename must route to the dispute-flip path.
    RED before Part B (gate returns True on age+voice alone → renames = the canary)."""
    import pipeline as _pl

    pid = "jagan_bf_gt2"
    _pl._session_store._sessions.pop(pid, None)
    await _pl._session_store.open_session(pid, "Jagan", "best_friend", "face", now=_t.time())
    # 50-turn established conversation — far past the enrollment moment.
    _pl._session_store._sessions[pid].user_turns = 50
    snap = _pl._session_store.peek_snapshot(pid)
    assert snap.user_turns == 50

    mock_db = MagicMock()
    mock_db.voice_embedding_count.return_value = 0  # empty gallery (Part A bug state)

    assert _pl._is_enrollment_mishear_candidate(mock_db, pid, snap) is False, (
        "a 50-turn best_friend must NOT qualify as an enrollment-mishear candidate"
    )


@pytest.mark.asyncio
async def test_gt2_voice_only_claim_does_not_rename_established_best_friend():
    """GT2 (e2e): a grounded 'my name is Lexi' on a 50-turn best_friend session must NOT
    migrate the person's name — it routes to dispute. RED before Part B (renames =
    the exact Jagan→Lexi corruption)."""
    import asyncio
    import pipeline as _pl
    from pipeline import _execute_tool

    pid = "jagan_bf_gt2e2e"
    _pl._session_store._sessions.pop(pid, None)
    await _pl._session_store.open_session(pid, "Jagan", "best_friend", "face", now=_t.time())
    _pl._session_store._sessions[pid].user_turns = 50
    await _pl._conversation_store.set_history(pid, [])

    mock_db = MagicMock()
    mock_db.voice_embedding_count.return_value = 0

    orig_orch = _pl._brain_orchestrator
    _pl._brain_orchestrator = MagicMock()
    try:
        await _execute_tool(
            "update_person_name", {"name": "Lexi"},
            pid, "Jagan", db=mock_db,
            user_text="my name is Lexi",
        )
        await asyncio.sleep(0)  # flush transition_to_disputed create_task
    finally:
        _pl._brain_orchestrator = orig_orch

    mock_db.update_person_name.assert_not_called()
    assert _pl._session_store.peek_snapshot(pid).person_type == "disputed", (
        "an established best_friend rename claim must flip to disputed, not rename"
    )


# ── GT2-companion (PI-1) — genuine turn-1 enrollment-mishear STILL renames ─────


@pytest.mark.asyncio
async def test_gt2_companion_fresh_turn1_best_friend_still_renames():
    """PI-1 (symmetric verification): a turn-1 fresh best_friend (user_turns <= 3, within
    grace, voice_n=0) + grounded claim STILL qualifies → genuine enrollment-mishear
    correction is preserved. Proves B1 doesn't over-restrict. GREEN before AND after B1."""
    import pipeline as _pl

    pid = "jagan_bf_companion"
    _pl._session_store._sessions.pop(pid, None)
    await _pl._session_store.open_session(pid, "Gevan", "best_friend", "face", now=_t.time())
    # Explicit in-window turn count (PI-1: intentional, not the incidental default 0).
    _pl._session_store._sessions[pid].user_turns = 2
    snap = _pl._session_store.peek_snapshot(pid)
    assert snap.user_turns == 2

    mock_db = MagicMock()
    mock_db.voice_embedding_count.return_value = 0

    assert _pl._is_enrollment_mishear_candidate(mock_db, pid, snap) is True, (
        "a genuine turn-1 fresh-enrollment mishear (user_turns<=3) must STILL qualify"
    )


# ── Q2-unit — subprocess loader routes through the shared patch helper ────────


def test_q2_subprocess_ecapa_routes_through_shared_patch_helper():
    """Q2 (always-CI, no GPU): _get_subprocess_ecapa must obtain its classifier through
    the shared patch helper voice._load_ecapa_patched — NOT a bare EncoderClassifier
    .from_hparams (which is exactly the missing-patch bug). Source-inspection guard so CI
    has a check even without the GPU that GT1 needs."""
    import core.heavy_worker as hw
    src = inspect.getsource(hw._get_subprocess_ecapa)
    assert "_load_ecapa_patched" in src, (
        "_get_subprocess_ecapa must call the shared voice._load_ecapa_patched helper"
    )
    # Check for the CALL form `from_hparams(` (a comment may legitimately mention the word).
    assert "from_hparams(" not in src, (
        "_get_subprocess_ecapa must NOT call from_hparams directly — that bypasses the patch"
    )


# ── A2-guard — every SpeechBrain from_hparams reached only via the helper ─────


_PATCH_HELPER = "_load_ecapa_patched"


def _from_hparams_callsites(path: Path) -> list[tuple[str, int]]:
    """Return (enclosing_function_name, lineno) for every `*.from_hparams(...)` call."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    # Map each function def to its (start, end) line span.
    funcs = [
        (n.name, n.lineno, n.end_lineno)
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]

    def enclosing(lineno: int) -> str:
        best = "<module>"
        best_start = -1
        for name, s, e in funcs:
            if s <= lineno <= (e or s) and s > best_start:
                best, best_start = name, s
        return best

    out: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "from_hparams"
        ):
            out.append((enclosing(node.lineno), node.lineno))
    return out


def test_a2_guard_from_hparams_only_in_shared_patch_helper():
    """A2-guard (P0.5 bidirectional inverse-check, always-CI): EVERY SpeechBrain
    `from_hparams` call across core/voice.py + core/heavy_worker.py must sit inside the
    shared patch helper `_load_ecapa_patched`. The helper applies the hf_hub_download
    patch before the call; any from_hparams OUTSIDE it loads SpeechBrain unpatched — the
    exact bug P0.R6.Y introduced. This is the guard GT1 (GPU-gated) cannot provide on CI."""
    offenders: list[str] = []
    for rel in ("core/voice.py", "core/heavy_worker.py"):
        for fn, ln in _from_hparams_callsites(REPO_ROOT / rel):
            if fn != _PATCH_HELPER:
                offenders.append(f"{rel}:{ln} (in {fn!r})")
    assert not offenders, (
        "SpeechBrain from_hparams reached OUTSIDE the shared patch helper "
        f"{_PATCH_HELPER!r} (loads SpeechBrain without the hf_hub_download patch — the "
        f"Canary #3 / P0.R6.Y bug class):\n  " + "\n  ".join(offenders)
    )


def test_a2_guard_helper_patches_before_from_hparams():
    """A2-guard companion: the shared helper must apply the hf_hub_download patch (assign
    `hf_hub_download = ...`) BEFORE its from_hparams call — the two-phase ordering is the
    whole point (SpeechBrain captures the symbol at import time)."""
    # Read the REAL file from disk — conftest stubs `core.voice` in sys.modules, so the
    # imported module would not carry the real helper.
    module_tree = ast.parse((REPO_ROOT / "core/voice.py").read_text(encoding="utf-8"))
    helper_node = next(
        (n for n in ast.walk(module_tree)
         if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == _PATCH_HELPER),
        None,
    )
    assert helper_node is not None, f"core/voice.py must define {_PATCH_HELPER}"
    patch_line = None
    fromh_line = None
    for node in ast.walk(helper_node):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Attribute) and tgt.attr == "hf_hub_download":
                    patch_line = node.lineno if patch_line is None else min(patch_line, node.lineno)
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "from_hparams"):
            fromh_line = node.lineno if fromh_line is None else min(fromh_line, node.lineno)
    assert patch_line is not None, "helper must assign hf_hub_download (apply the patch)"
    assert fromh_line is not None, "helper must call from_hparams"
    assert patch_line < fromh_line, (
        "the hf_hub_download patch MUST precede from_hparams (two-phase ordering)"
    )
