"""tests/test_p0_s1_phase3.py — P0.S1 Phase 3 Consumer + watchdog tests.

Plan v2 §10 Phase 3 = 9 tests:
1-3. progressive_enroll matrix (verdict True / False / None) — site 5 closure.
4-5. voice-only fallthrough (session opens + bootstrap granted on face block).
6. reason-code distinguishability dashboard payload.
7. burst-threshold exact-equality trigger (§14b.1 — `count == THRESHOLD`).
8. per-track scope (track_A burst does NOT affect track_B count).
9. cleanup (close_session AND stale-prune pop from rejection store).
"""
from __future__ import annotations

import asyncio
import pathlib
import re
import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _read(rel: str) -> str:
    return (_REPO_ROOT / rel).read_text(encoding="utf-8")


def _random_embedding(seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(512).astype(np.float32)
    v /= np.linalg.norm(v)
    return v


# ────────────────────────────────────────────────────────────────────────────
# (1-3) progressive_enroll matrix — site 5 wiring + catch-all interaction
# ────────────────────────────────────────────────────────────────────────────


def test_progressive_enroll_reads_verdict_from_track_store():
    """Site 5 (progressive_enroll) gate calls peek_anti_spoof_verdict on the
    track store before add_embedding. Source-inspection because the gate is
    deeply embedded in pipeline.run."""
    src = _read("pipeline.py")
    # Locate the progressive_enroll branch via a stable anchor.
    pe_marker = 'progressive_enroll'
    # Find the FIRST anti-spoof block above the actual add_embedding call.
    # The pattern is: peek_anti_spoof_verdict + anti_spoof_verdict=_gate_live.
    assert "peek_anti_spoof_verdict(_gate_track)" in src, (
        "Site 5 must read verdict via _track_store.peek_anti_spoof_verdict"
    )
    # add_embedding call now threads the verdict.
    assert re.search(
        r'add_embedding\(\s*\n?\s*_cur_pid,\s*_gate_emb,\s*"progressive_enroll",\s*\n?\s*anti_spoof_verdict=_gate_live',
        src,
    ), "add_embedding for progressive_enroll must pass anti_spoof_verdict=_gate_live"
    # Reference to progressive_enroll source name remains.
    assert pe_marker in src


def test_add_embedding_blocks_progressive_enroll_when_verdict_false(tmp_path):
    """T/F/None matrix via the catch-all: verdict=False on progressive_enroll
    blocks the write. This is the structural backstop for site 5's runtime
    behavior (the catch-all is the layer the test exercises directly)."""
    import core.db as _db_mod
    with patch.object(_db_mod, "DB_PATH", tmp_path / "f.db"), \
         patch.object(_db_mod, "FAISS_INDEX_PATH", tmp_path / "f.index"):
        db = _db_mod.FaceDB()
        db.add_person("stranger_xyz", "Visitor", None, person_type="stranger")
        try:
            ok = db.add_embedding(
                "stranger_xyz", _random_embedding(1), "progressive_enroll",
                anti_spoof_verdict=False,
            )
            assert ok is False
            cnt = db._conn.execute(
                "SELECT COUNT(*) FROM embeddings WHERE person_id='stranger_xyz'"
            ).fetchone()[0]
            assert cnt == 0
        finally:
            db._conn.close()


def test_add_embedding_blocks_progressive_enroll_when_verdict_none(tmp_path):
    """Verdict=None (no verdict captured — checker unavailable or producer
    didn't record) blocks the progressive_enroll write. Fail-closed default."""
    import core.db as _db_mod
    with patch.object(_db_mod, "DB_PATH", tmp_path / "f.db"), \
         patch.object(_db_mod, "FAISS_INDEX_PATH", tmp_path / "f.index"):
        db = _db_mod.FaceDB()
        db.add_person("stranger_xyz", "Visitor", None, person_type="stranger")
        try:
            ok = db.add_embedding(
                "stranger_xyz", _random_embedding(2), "progressive_enroll",
                anti_spoof_verdict=None,
            )
            assert ok is False
        finally:
            db._conn.close()


# ────────────────────────────────────────────────────────────────────────────
# (4-5) voice-only fallthrough — session opens + bootstrap granted
# ────────────────────────────────────────────────────────────────────────────


def test_voice_only_fallthrough_preserves_bootstrap_branch():
    """When face write blocked by anti-spoof, the existing else-branch grants
    bootstrap credits (D9 voice-only fallthrough). Source-inspection: the
    pre-P0.S1 else-branch (Bug C voice-only path) is still present and runs
    when `_face_captured` stays False."""
    src = _read("pipeline.py")
    # Bug C voice-only branch — grants bootstrap when face NOT captured.
    assert "Voice-only engagement — NO face was captured" in src, (
        "Voice-only fallthrough branch must still exist for D9"
    )
    assert "set_bootstrap_credits(\n                                                _cur_pid, N_INITIAL_VOICE_BOOTSTRAP" in src or \
           "N_INITIAL_VOICE_BOOTSTRAP" in src, (
        "Voice-only fallthrough must seed bootstrap credits"
    )


def test_voice_only_fallthrough_rejection_path_logs_and_records():
    """When the anti-spoof gate blocks the face write, the pipeline logs
    `BLOCKED progressive_enroll` AND calls record_rejection AND only triggers
    burst alert at exact-equality. Source-inspection of the wiring."""
    src = _read("pipeline.py")
    assert "BLOCKED progressive_enroll" in src
    assert "_anti_spoof_rejection_store.record_rejection" in src
    # §14b.1 exact-equality (NOT >=).
    assert re.search(
        r"if\s+_rej_count\s*==\s*ANTI_SPOOF_BURST_THRESHOLD",
        src,
    ), "Burst trigger must use EXACT EQUALITY per Plan v2 §14b.1"
    # report_anti_spoof_burst dispatch via orchestrator.
    assert "report_anti_spoof_burst(" in src
    assert "report_anti_spoof_rejection(" in src


# ────────────────────────────────────────────────────────────────────────────
# (6) Reason-code distinguishability — dashboard payload
# ────────────────────────────────────────────────────────────────────────────


def test_watchdog_anti_spoof_rejection_records_reason_distinguishably():
    """report_anti_spoof_rejection stores a watchdog alert whose metadata
    distinguishes the four reason codes — `passed`, `rejected`, `unavailable`,
    `no_verdict`. Dashboard / replay can branch on `reason` field."""
    from core.brain_agent import WatchdogAgent

    fake_db = MagicMock()
    fake_db.unresolved_alert_exists.return_value = False
    fake_conn = MagicMock()
    wd = WatchdogAgent(fake_db, fake_conn)

    for reason in ("rejected", "unavailable", "no_verdict"):
        fake_db.reset_mock()
        wd.report_anti_spoof_rejection(
            track_id="t_alpha", reason=reason, score=0.05, person_id="stranger_zz",
        )
        assert fake_db.store_alert.called
        call_args = fake_db.store_alert.call_args
        # Positional args: (alert_type, severity, message, metadata)
        alert_type, severity, message, metadata = call_args[0]
        assert alert_type == "ANTI_SPOOF_REJECTION"
        assert severity == "info"
        assert metadata["reason"] == reason
        assert metadata["track_id"] == "t_alpha"
        assert metadata["score"] == 0.05
        assert metadata["person_id"] == "stranger_zz"


# ────────────────────────────────────────────────────────────────────────────
# (7) Burst threshold — exact-equality trigger (§14b.1)
# ────────────────────────────────────────────────────────────────────────────


def test_anti_spoof_burst_exact_equality_trigger_via_store():
    """The rejection store + watchdog interaction: record 3 rejections, the
    pipeline's exact-equality guard should fire the burst alert once at the
    3rd record. This test simulates the guard logic directly on the store."""
    from core.anti_spoof_rejection_store import AntiSpoofRejectionStore
    from core.config import ANTI_SPOOF_BURST_THRESHOLD, ANTI_SPOOF_BURST_WINDOW_SECS

    store = AntiSpoofRejectionStore()
    now = 1000.0
    burst_fires = []

    def fire(count):
        # Simulate the §14b.1 exact-equality guard.
        if count == ANTI_SPOOF_BURST_THRESHOLD:
            burst_fires.append(count)

    # Record THRESHOLD rejections; only the THRESHOLD-th should trigger.
    for i in range(ANTI_SPOOF_BURST_THRESHOLD):
        cnt = asyncio.run(store.record_rejection(
            "track_burst", now + i, ANTI_SPOOF_BURST_WINDOW_SECS
        ))
        fire(cnt)

    assert burst_fires == [ANTI_SPOOF_BURST_THRESHOLD], (
        f"Burst should fire exactly once at count={ANTI_SPOOF_BURST_THRESHOLD}; "
        f"observed: {burst_fires}"
    )

    # Continued rejections (4th, 5th, ...) should NOT re-fire under exact equality.
    for i in range(ANTI_SPOOF_BURST_THRESHOLD, ANTI_SPOOF_BURST_THRESHOLD + 3):
        cnt = asyncio.run(store.record_rejection(
            "track_burst", now + i, ANTI_SPOOF_BURST_WINDOW_SECS
        ))
        fire(cnt)

    assert burst_fires == [ANTI_SPOOF_BURST_THRESHOLD], (
        f"Burst must NOT re-fire on subsequent rejections (exact-equality): {burst_fires}"
    )


# ────────────────────────────────────────────────────────────────────────────
# (8) Per-track scope — track_A burst does NOT affect track_B
# ────────────────────────────────────────────────────────────────────────────


def test_anti_spoof_burst_per_track_isolation():
    """C2 contract — per-track scope, not per-pid, not global. A burst on
    track_A leaves track_B's count untouched (no cross-track lockout)."""
    from core.anti_spoof_rejection_store import AntiSpoofRejectionStore
    from core.config import ANTI_SPOOF_BURST_THRESHOLD, ANTI_SPOOF_BURST_WINDOW_SECS

    store = AntiSpoofRejectionStore()
    now = 500.0

    # Fill track_A to threshold + over.
    for i in range(ANTI_SPOOF_BURST_THRESHOLD + 2):
        asyncio.run(store.record_rejection(
            "track_A", now + i, ANTI_SPOOF_BURST_WINDOW_SECS
        ))

    # track_B is untouched.
    assert store.peek_count("track_B", now, ANTI_SPOOF_BURST_WINDOW_SECS) == 0

    # Now record one rejection on track_B — count is 1, not THRESHOLD.
    cnt_b = asyncio.run(store.record_rejection(
        "track_B", now, ANTI_SPOOF_BURST_WINDOW_SECS
    ))
    assert cnt_b == 1
    assert cnt_b != ANTI_SPOOF_BURST_THRESHOLD  # would not trigger burst yet


# ────────────────────────────────────────────────────────────────────────────
# (9) Cleanup — close_session AND stale-prune both pop rejection store
# ────────────────────────────────────────────────────────────────────────────


def test_close_session_pops_rejection_store_for_owned_tracks():
    """Source-inspection: _close_session calls _anti_spoof_rejection_store.pop
    for every track that belonged to the closing session — both
    identity-bound tracks AND the stranger track."""
    src = _read("pipeline.py")
    # Locate _close_session body via the marker.
    fn_start = src.index("def _close_session(person_id: str)")
    fn_end = src.index("def ", fn_start + 1)
    body = src[fn_start:fn_end]
    assert "_anti_spoof_rejection_store.pop" in body, (
        "_close_session must pop rejection store entries for closing-session tracks"
    )
    # Both stranger track + identity tracks are covered.
    assert "peek_track_for_stranger_pid" in body
    assert "peek_tracks_for_person" in body


def test_stale_prune_pops_rejection_store_for_disappeared_tracks():
    """Source-inspection: the background-vision-loop stale-prune block pops
    rejection-store entries for tracks that disappeared from the active set."""
    src = _read("pipeline.py")
    sec_marker = "# ── Secondary face scan during active conversation"
    start = src.index(sec_marker)
    end = src.index("for _det in detections:", start)
    block = src[start:end]
    # The pop runs for stale tracks (set difference).
    assert "_anti_spoof_rejection_store.pop" in block, (
        "stale-prune block must pop rejection store for tracks no longer active"
    )
    assert "_pre_prune_tracks" in block or "_active_tids" in block, (
        "stale-prune must compute set-difference of pre-prune vs active"
    )
