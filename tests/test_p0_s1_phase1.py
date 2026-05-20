"""tests/test_p0_s1_phase1.py — P0.S1 Phase 1 Foundation tests.

Plan v2 §10 Phase 1 = 17 new tests:
- 5 TrackStore verdict-extension behavioral (init / upsert / peek / pop / reset)
- 1 frozenset invariant (ALLOWED_EMBEDDING_SOURCES_REQUIRING_ANTI_SPOOF shape)
- 3 add_embedding catch-all (verdict True / False / None)
- 3 enrollment-site migration verification (sites 1-4 AST/source-inspection)
- 1 TrackStore concurrency stress (MED 6 — Plan v2 §7)
- 4 AntiSpoofRejectionStore (record / peek / pop / concurrency stress)

Plus 5 pre-existing tests updated (in test_faiss_delete.py + test_pipeline.py)
threading anti_spoof_verdict=True through pre-P0.S1 add_embedding calls.
"""
from __future__ import annotations

import ast
import asyncio
import pathlib
import time
from unittest.mock import patch

import numpy as np
import pytest


# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────

_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _random_embedding(seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(512).astype(np.float32)
    v /= np.linalg.norm(v)
    return v


# ────────────────────────────────────────────────────────────────────────────
# (1) Frozenset invariant — Plan v2 §1
# ────────────────────────────────────────────────────────────────────────────


def test_allowed_anti_spoof_sources_equals_valid_after_legacy_unknown_drop():
    """P0.S1 D4 — `legacy_unknown` must be gone from VALID; ALLOWED == VALID."""
    from core.db import (
        VALID_EMBEDDING_SOURCES,
        ALLOWED_EMBEDDING_SOURCES_REQUIRING_ANTI_SPOOF,
    )

    # Post-D4: VALID has exactly the 3 production-callable sources.
    assert VALID_EMBEDDING_SOURCES == frozenset({
        "enrollment", "recognition_update", "progressive_enroll",
    })
    # legacy_unknown deleted — restoration requires explicit architect approval.
    assert "legacy_unknown" not in VALID_EMBEDDING_SOURCES

    # Every valid source requires anti-spoof gating after the drop.
    assert ALLOWED_EMBEDDING_SOURCES_REQUIRING_ANTI_SPOOF == VALID_EMBEDDING_SOURCES

    # Type discipline — frozenset (closed-world enforcement).
    assert isinstance(VALID_EMBEDDING_SOURCES, frozenset)
    assert isinstance(ALLOWED_EMBEDDING_SOURCES_REQUIRING_ANTI_SPOOF, frozenset)


# ────────────────────────────────────────────────────────────────────────────
# (2-4) add_embedding catch-all matrix — Plan v2 §1 / §10
# ────────────────────────────────────────────────────────────────────────────


def _fresh_db(tmp_path):
    import core.db as _db_mod
    db_path = tmp_path / "faces.db"
    idx_path = tmp_path / "faiss.index"
    with patch.object(_db_mod, "DB_PATH", db_path), \
         patch.object(_db_mod, "FAISS_INDEX_PATH", idx_path):
        db = _db_mod.FaceDB()
        db.add_person("p1", "Alice", None)
        return db


def test_add_embedding_catch_all_accepts_verdict_true(tmp_path):
    """Catch-all accepts protected source when verdict=True."""
    db = _fresh_db(tmp_path)
    try:
        ok = db.add_embedding(
            "p1", _random_embedding(1), "enrollment",
            anti_spoof_verdict=True,
        )
        assert ok is True
        row = db._conn.execute(
            "SELECT source FROM embeddings WHERE person_id='p1'"
        ).fetchone()
        assert row[0] == "enrollment"
    finally:
        db._conn.close()


def test_add_embedding_catch_all_rejects_verdict_false(tmp_path):
    """Catch-all rejects protected source when verdict=False."""
    db = _fresh_db(tmp_path)
    try:
        ok = db.add_embedding(
            "p1", _random_embedding(2), "enrollment",
            anti_spoof_verdict=False,
        )
        assert ok is False
        # Zero rows written.
        cnt = db._conn.execute(
            "SELECT COUNT(*) FROM embeddings WHERE person_id='p1'"
        ).fetchone()[0]
        assert cnt == 0
    finally:
        db._conn.close()


def test_add_embedding_catch_all_rejects_verdict_none(tmp_path):
    """Catch-all rejects protected source when verdict is None (default)."""
    db = _fresh_db(tmp_path)
    try:
        ok = db.add_embedding(
            "p1", _random_embedding(3), "recognition_update",
            anti_spoof_verdict=None,
        )
        assert ok is False
        cnt = db._conn.execute(
            "SELECT COUNT(*) FROM embeddings WHERE person_id='p1'"
        ).fetchone()[0]
        assert cnt == 0
    finally:
        db._conn.close()


# ────────────────────────────────────────────────────────────────────────────
# (5-7) Enrollment-site migration verification — Plan v2 §2 / §3
# ────────────────────────────────────────────────────────────────────────────


def _read(rel: str) -> str:
    return (_REPO_ROOT / rel).read_text(encoding="utf-8")


def test_first_boot_flow_threads_anti_spoof_verdict():
    """Site 1: pipeline.first_boot_flow captures and threads verdict."""
    src = _read("pipeline.py")
    # Verdict captured in a local before the gate.
    assert "_fb_verdict = verify_live(" in src
    # And passed through to add_embedding.
    assert "anti_spoof_verdict=_verdict" in src or \
           "anti_spoof_verdict=_fb_verdict" in src


def test_enrollment_flow_threads_anti_spoof_verdict():
    """Sites 2 (pipeline.enrollment_flow) and 3 (enroll.py CLI): same pattern."""
    pipeline_src = _read("pipeline.py")
    enroll_src = _read("enroll.py")
    assert "_en_verdict = verify_live(" in pipeline_src
    assert "_en_verdict = verify_live(" in enroll_src
    # Both call sites pass anti_spoof_verdict=_verdict in the tuple-unpacked loop.
    assert pipeline_src.count("anti_spoof_verdict=_verdict") >= 2 or \
           pipeline_src.count("anti_spoof_verdict=_en_verdict") >= 1
    assert "anti_spoof_verdict=_verdict" in enroll_src


def test_recognition_update_threads_anti_spoof_verdict():
    """Site 4: pipeline recognition_update path passes verdict=_anti_spoof_ok."""
    src = _read("pipeline.py")
    assert "anti_spoof_verdict=_anti_spoof_ok" in src


# ────────────────────────────────────────────────────────────────────────────
# (8-12) TrackStore verdict-extension behavioral — Plan v2 §4 / §8
# ────────────────────────────────────────────────────────────────────────────


def test_track_store_initial_snapshot_has_none_verdict():
    """Fresh TrackEntry has anti_spoof_live=None (no verdict captured yet)."""
    from core.track_store import TrackStore
    store = TrackStore()
    asyncio.run(store.mark_unrecognized(42, time.time()))
    snap = store.peek_snapshot(42)
    assert snap is not None
    assert snap.anti_spoof_live is None
    assert snap.anti_spoof_score is None
    assert snap.anti_spoof_reason is None
    assert snap.captured_at == 0.0
    assert snap.bbox is None


def test_track_store_upsert_with_verdict_atomic_observation():
    """upsert_embedding_with_verdict writes embedding + verdict atomically."""
    from core.track_store import TrackStore
    store = TrackStore()
    emb = _random_embedding(10)
    now = time.time()
    asyncio.run(store.upsert_embedding_with_verdict(
        track_id=7,
        embedding=emb,
        anti_spoof_live=True,
        anti_spoof_score=0.95,
        anti_spoof_reason="passed",
        captured_at=now,
        bbox=(10, 20, 30, 40),
    ))
    snap = store.peek_snapshot(7)
    assert snap is not None
    # Both fields visible together.
    assert snap.embedding is emb
    assert snap.anti_spoof_live is True
    assert snap.anti_spoof_score == 0.95
    assert snap.anti_spoof_reason == "passed"
    assert snap.captured_at == now
    assert snap.bbox == (10, 20, 30, 40)


def test_track_store_peek_anti_spoof_verdict_returns_tuple():
    """peek_anti_spoof_verdict returns (live, score, reason) or all-None."""
    from core.track_store import TrackStore
    store = TrackStore()
    # Unknown track → all-None.
    assert store.peek_anti_spoof_verdict("nonexistent") == (None, None, None)
    # Known track → fields.
    asyncio.run(store.upsert_embedding_with_verdict(
        track_id=3, embedding=_random_embedding(11),
        anti_spoof_live=False, anti_spoof_score=0.02,
        anti_spoof_reason="rejected", captured_at=time.time(),
    ))
    assert store.peek_anti_spoof_verdict(3) == (False, 0.02, "rejected")


def test_track_store_pop_clears_verdict():
    """remove_track removes the entry entirely — peek returns None."""
    from core.track_store import TrackStore
    store = TrackStore()
    asyncio.run(store.upsert_embedding_with_verdict(
        track_id=99, embedding=_random_embedding(12),
        anti_spoof_live=True, anti_spoof_score=0.9,
        anti_spoof_reason="passed", captured_at=time.time(),
    ))
    asyncio.run(store.remove_track(99))
    assert store.peek_snapshot(99) is None
    assert store.peek_anti_spoof_verdict(99) == (None, None, None)


def test_track_store_reset_clears_verdict():
    """reset() clears all entries including verdict-carrying ones."""
    from core.track_store import TrackStore
    store = TrackStore()
    asyncio.run(store.upsert_embedding_with_verdict(
        track_id=1, embedding=_random_embedding(13),
        anti_spoof_live=True, anti_spoof_score=0.88,
        anti_spoof_reason="passed", captured_at=time.time(),
    ))
    assert store.peek_count() == 1
    store.reset()
    assert store.peek_count() == 0
    assert store.peek_snapshot(1) is None


# ────────────────────────────────────────────────────────────────────────────
# (13) TrackStore concurrency stress — Plan v2 §7 (MED 6)
# ────────────────────────────────────────────────────────────────────────────


def test_track_store_upsert_with_verdict_is_atomically_observable():
    """Under concurrent writer + 50 readers, peek_snapshot NEVER returns a torn
    state where embedding is set without verdict (or vice versa)."""
    from core.track_store import TrackStore
    store = TrackStore()

    torn_observations: list = []

    async def writer():
        for i in range(100):
            emb = _random_embedding(i)
            await store.upsert_embedding_with_verdict(
                track_id=42,
                embedding=emb,
                anti_spoof_live=True,
                anti_spoof_score=0.9,
                anti_spoof_reason="passed",
                captured_at=time.time(),
            )
            await asyncio.sleep(0.0001)

    async def reader():
        # Run many peeks during the writer's burst.
        for _ in range(500):
            snap = store.peek_snapshot(42)
            if snap is not None:
                # Torn-state check: embedding present iff verdict present.
                emb_set = snap.embedding is not None
                verdict_set = snap.anti_spoof_live is not None
                if emb_set != verdict_set:
                    torn_observations.append(
                        (emb_set, verdict_set, snap.anti_spoof_reason)
                    )
            await asyncio.sleep(0)

    async def main():
        await asyncio.gather(writer(), *[reader() for _ in range(50)])

    asyncio.run(main())

    assert torn_observations == [], (
        f"Torn-state observations: {len(torn_observations)}; first 3: "
        f"{torn_observations[:3]}"
    )


# ────────────────────────────────────────────────────────────────────────────
# (14-17) AntiSpoofRejectionStore — Plan v2 §4
# ────────────────────────────────────────────────────────────────────────────


def test_anti_spoof_rejection_store_record_and_peek():
    """record_rejection increments count; peek_count agrees."""
    from core.anti_spoof_rejection_store import AntiSpoofRejectionStore
    store = AntiSpoofRejectionStore()
    now = 1000.0
    window = 60.0

    n1 = asyncio.run(store.record_rejection("track_A", now, window))
    assert n1 == 1
    n2 = asyncio.run(store.record_rejection("track_A", now + 1, window))
    assert n2 == 2
    assert store.peek_count("track_A", now + 1, window) == 2


def test_anti_spoof_rejection_store_window_prune():
    """Entries older than window are pruned on every record + peek."""
    from core.anti_spoof_rejection_store import AntiSpoofRejectionStore
    store = AntiSpoofRejectionStore()
    window = 60.0

    asyncio.run(store.record_rejection("t1", 0.0, window))
    asyncio.run(store.record_rejection("t1", 30.0, window))
    asyncio.run(store.record_rejection("t1", 70.0, window))  # prunes 0.0 (>60s old)
    # Cutoff at 70.0 - 60.0 = 10.0 → 30.0 and 70.0 survive.
    assert store.peek_count("t1", 70.0, window) == 2
    # At 200s, both are stale.
    assert store.peek_count("t1", 200.0, window) == 0


def test_anti_spoof_rejection_store_per_track_scope():
    """Per-track scope: track_A burst does NOT affect track_B count (C2)."""
    from core.anti_spoof_rejection_store import AntiSpoofRejectionStore
    store = AntiSpoofRejectionStore()
    now = 100.0
    window = 60.0

    for _ in range(5):
        asyncio.run(store.record_rejection("track_A", now, window))

    # track_B unaffected.
    assert store.peek_count("track_B", now, window) == 0
    assert store.peek_count("track_A", now, window) == 5

    # Pop track_A — track_B still untouched.
    asyncio.run(store.pop("track_A"))
    assert store.peek_count("track_A", now, window) == 0
    assert store.peek_count("track_B", now, window) == 0


def test_anti_spoof_rejection_store_reset_and_stress():
    """reset() clears all tracks; concurrent recorders never lose increments."""
    from core.anti_spoof_rejection_store import AntiSpoofRejectionStore
    store = AntiSpoofRejectionStore()

    # Concurrency stress — N tasks each recording M rejections.
    N_TASKS = 20
    M_RECORDS = 25
    now = 500.0
    window = 1000.0  # large window so no pruning

    async def recorder(track_id: str):
        for i in range(M_RECORDS):
            await store.record_rejection(track_id, now + i * 0.001, window)

    async def main():
        await asyncio.gather(*[recorder(f"track_{k}") for k in range(N_TASKS)])

    asyncio.run(main())

    # Every track should have exactly M_RECORDS entries (no lost increments).
    for k in range(N_TASKS):
        cnt = store.peek_count(f"track_{k}", now + M_RECORDS, window)
        assert cnt == M_RECORDS, f"track_{k} expected {M_RECORDS} got {cnt}"

    # reset clears everything.
    store.reset()
    assert store.peek_track_count() == 0
    for k in range(N_TASKS):
        assert store.peek_count(f"track_{k}", now, window) == 0


# ────────────────────────────────────────────────────────────────────────────
# Bonus invariant: config constants present + threshold sanity
# ────────────────────────────────────────────────────────────────────────────


def test_anti_spoof_burst_config_constants_present():
    """Plan v2 §11 — config constants exist with sane values."""
    import core.config as cfg

    assert cfg.ANTI_SPOOF_BURST_THRESHOLD == 3
    assert cfg.ANTI_SPOOF_BURST_WINDOW_SECS == 60.0
    assert cfg.ANTI_SPOOF_REASON_PASSED == "passed"
    assert cfg.ANTI_SPOOF_REASON_REJECTED == "rejected"
    assert cfg.ANTI_SPOOF_REASON_UNAVAILABLE == "unavailable"
    assert cfg.ANTI_SPOOF_REASON_NO_VERDICT == "no_verdict"

    # Threshold sanity — positive integer.
    assert cfg.ANTI_SPOOF_BURST_THRESHOLD >= 1
    assert cfg.ANTI_SPOOF_BURST_WINDOW_SECS > 0.0
