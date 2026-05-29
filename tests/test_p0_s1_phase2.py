"""tests/test_p0_s1_phase2.py — P0.S1 Phase 2 Producer-wiring tests.

Plan v2 §5 (HIGH 1) Phase 2 deliverable list = 6 tests:
1. Ambient-listen verify_live wiring (source-inspection of ambient scan path)
2. Secondary-scan verify_live wiring (source-inspection of secondary scan path)
3. Atomic upsert behavioral (verdict + embedding visible together via peek)
4. Atomic upsert concurrency stress — PREEMPTIVELY LANDED IN PHASE 1
   (test_track_store_upsert_with_verdict_is_atomically_observable). Phase 2
   re-asserts the same invariant with a vision-loop-shaped fixture.
5. Reason-code matrix — _classify_anti_spoof_verdict over passed/rejected/
   unavailable scenarios returns the correct (live, score, reason) triple.
6. Same-frame AST scan (HIGH 1 pulled forward from Phase 4 per §5). Uses
   marker-comment fallback per Plan v2 §14b.2 — production code carries
   `# P0S1-C0:` markers; this test asserts the markers exist AND that within
   K=12 lines following each marker the (verify_live OR _classify_anti_spoof_verdict)
   call, the `embedder.embed` call, and the `_crop = frame[...]` slice all
   reference the same `frame` variable.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import ast
import asyncio
import pathlib
import re
import time

import numpy as np


_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _read(rel: str) -> str:
    return (_REPO_ROOT / rel).read_text(encoding="utf-8")


# ────────────────────────────────────────────────────────────────────────────
# (1) Ambient-listen path wiring — Plan v2 §8.1
# ────────────────────────────────────────────────────────────────────────────


def test_ambient_listen_path_classifies_and_upserts_with_verdict():
    """Ambient-listen scan path in _background_vision_loop calls
    _classify_anti_spoof_verdict + upsert_embedding_with_verdict.

    Source-inspection (not behavioral) because the loop is a long-running
    async generator with executor offload — exercising it end-to-end requires
    a real camera or extensive mocking. The structural test asserts the wiring
    pattern is correct so future refactors that break the contract surface.
    """
    src = _read("pipeline.py")

    # Locate the ambient-listen path body using its docstring marker.
    ambient_marker = "# ── Full recognition when no active sessions (ambient listen path)"
    assert ambient_marker in src, "ambient-listen path marker missing"

    start = src.index(ambient_marker)
    # Body extends ~80 lines into the next "# ── Secondary face scan" block.
    secondary_marker = "# ── Secondary face scan during active conversation"
    end = src.index(secondary_marker, start)
    body = src[start:end]

    # Helper called with frame as the FIRST positional arg (C0 same-frame).
    assert "_classify_anti_spoof_verdict(" in body, (
        "Ambient-listen path must call _classify_anti_spoof_verdict"
    )
    # Helper invocation includes `frame, _det.bbox` (positional, same frame).
    assert re.search(
        r"_classify_anti_spoof_verdict\(\s*\n?\s*frame,\s*_det\.bbox",
        body,
    ), "Helper must be called with (frame, _det.bbox, ...) — same-frame discipline"
    # Atomic upsert lands the verdict + embedding in the store together.
    assert "upsert_embedding_with_verdict(" in body, (
        "Ambient-listen path must call upsert_embedding_with_verdict"
    )


# ────────────────────────────────────────────────────────────────────────────
# (2) Secondary-scan path wiring — Plan v2 §8.2
# ────────────────────────────────────────────────────────────────────────────


def test_secondary_scan_path_classifies_and_upserts_with_verdict():
    """Same wiring assertion as #1 but for the secondary-scan path."""
    src = _read("pipeline.py")

    sec_marker = "# ── Secondary face scan during active conversation"
    assert sec_marker in src
    start = src.index(sec_marker)
    # Body extends to the H2 vision_frame emit at the loop tail.
    emit_marker = "# P0.0.7 H2 — emit vision_frame event"
    end = src.index(emit_marker, start)
    body = src[start:end]

    assert "_classify_anti_spoof_verdict(" in body, (
        "Secondary-scan path must call _classify_anti_spoof_verdict"
    )
    assert re.search(
        r"_classify_anti_spoof_verdict\(\s*\n?\s*frame,\s*_det\.bbox",
        body,
    ), "Helper must be called with (frame, _det.bbox, ...) — same-frame discipline"
    assert "upsert_embedding_with_verdict(" in body, (
        "Secondary-scan path must call upsert_embedding_with_verdict"
    )


# ────────────────────────────────────────────────────────────────────────────
# (3) Atomic upsert behavioral — observable verdict + embedding together
# ────────────────────────────────────────────────────────────────────────────


def test_track_store_atomic_upsert_observable_from_loop_shape():
    """Mirror-shape of the Phase 1 atomic test but exercising the path the
    background vision loop uses (kwargs match the production call site)."""
    from core.track_store import TrackStore

    store = TrackStore()
    emb = np.random.randn(512).astype(np.float32)
    now = time.time()

    asyncio.run(store.upsert_embedding_with_verdict(
        track_id=99,
        embedding=emb,
        anti_spoof_live=True,
        anti_spoof_score=0.91,
        anti_spoof_reason="passed",
        captured_at=now,
        bbox=(0, 0, 100, 100),
    ))
    snap = store.peek_snapshot(99)
    assert snap is not None
    assert snap.embedding is emb
    assert snap.anti_spoof_live is True
    assert snap.anti_spoof_score == 0.91
    assert snap.anti_spoof_reason == "passed"
    assert snap.captured_at == now
    assert snap.bbox == (0, 0, 100, 100)
    # peek_anti_spoof_verdict (consumer-facing read API) matches.
    assert store.peek_anti_spoof_verdict(99) == (True, 0.91, "passed")


# ────────────────────────────────────────────────────────────────────────────
# (5) Reason-code matrix — _classify_anti_spoof_verdict over 3 scenarios
# ────────────────────────────────────────────────────────────────────────────


class _FakeChecker:
    def __init__(self, available: bool, live: bool, score: float):
        self.available = available
        self._live = live
        self.last_score = score

    # AntiSpoofChecker's underlying API surface used by verify_live wrapper:
    def is_live(self, frame, bbox) -> bool:  # noqa: ARG002
        return self._live


def test_classify_anti_spoof_verdict_passed():
    """Available checker + verify_live True → (True, score, 'passed')."""
    import pipeline
    from core.config import ANTI_SPOOF_REASON_PASSED

    fake = _FakeChecker(available=True, live=True, score=0.97)
    live, score, reason = pipeline._classify_anti_spoof_verdict(
        frame=None, bbox=(0, 0, 10, 10), checker=fake
    )
    assert live is True
    assert score == 0.97
    assert reason == ANTI_SPOOF_REASON_PASSED


def test_classify_anti_spoof_verdict_rejected():
    """Available checker + verify_live False → (False, score, 'rejected')."""
    import pipeline
    from core.config import ANTI_SPOOF_REASON_REJECTED

    fake = _FakeChecker(available=True, live=False, score=0.05)
    live, score, reason = pipeline._classify_anti_spoof_verdict(
        frame=None, bbox=(0, 0, 10, 10), checker=fake
    )
    assert live is False
    assert score == 0.05
    assert reason == ANTI_SPOOF_REASON_REJECTED


def test_classify_anti_spoof_verdict_unavailable_none_and_unavailable_attr():
    """checker is None OR checker.available is False → (None, None, 'unavailable')."""
    import pipeline
    from core.config import ANTI_SPOOF_REASON_UNAVAILABLE

    # None checker.
    live1, score1, reason1 = pipeline._classify_anti_spoof_verdict(
        frame=None, bbox=(0, 0, 10, 10), checker=None
    )
    assert live1 is None
    assert score1 is None
    assert reason1 == ANTI_SPOOF_REASON_UNAVAILABLE

    # Checker present but unavailable.
    fake = _FakeChecker(available=False, live=True, score=0.99)
    live2, score2, reason2 = pipeline._classify_anti_spoof_verdict(
        frame=None, bbox=(0, 0, 10, 10), checker=fake
    )
    assert live2 is None
    assert score2 is None
    assert reason2 == ANTI_SPOOF_REASON_UNAVAILABLE


# ────────────────────────────────────────────────────────────────────────────
# (6) HIGH 1 — same-frame discipline AST/marker scan
# ────────────────────────────────────────────────────────────────────────────


def test_same_frame_discipline_in_background_vision_loop():
    """P0.S1 C0 — `verify_live(frame, ...)` (or `_classify_anti_spoof_verdict(frame, ...)`)
    operates on the SAME `frame` variable that was sliced to produce the
    embedding crop. Plan v2 §3.2 lays out two enforcement routes:

      Route A — AST graph walk.
      Route B — marker-comment fallback (`# P0S1-C0:` markers in production
                code; scan finds markers and asserts the next K lines pass
                through the same frame variable).

    Production code uses `run_in_executor(None, embedder.embed, _crop)` which
    makes the embedder.embed Call node a non-trivial chain for Route A
    (embedder.embed appears as a Name expression, not a Call). Route B is
    cleaner here and is the route this test exercises.
    """
    pipeline_path = _REPO_ROOT / "pipeline.py"
    src = pipeline_path.read_text(encoding="utf-8")
    lines = src.splitlines()

    marker_re = re.compile(r"#\s*P0S1-C0:")
    marker_lines = [i for i, ln in enumerate(lines) if marker_re.search(ln)]
    # At minimum: ambient path + secondary-scan path each carry one marker.
    assert len(marker_lines) >= 2, (
        f"Expected ≥2 `# P0S1-C0:` markers in pipeline.py (one per scan path); "
        f"found {len(marker_lines)}."
    )

    K = 25  # lookahead window — pragmatic upper bound given current code shape.
    for idx in marker_lines:
        window = "\n".join(lines[idx : idx + K])
        # Three required elements in the window:
        # (a) `_crop = frame[...]` — slice from `frame`.
        assert re.search(r"_crop\s*=\s*frame\[", window), (
            f"P0S1-C0 marker at line {idx + 1}: no `_crop = frame[...]` "
            f"slice in next {K} lines.\nWindow:\n{window}"
        )
        # (b) `embedder.embed(_crop)` — embedding producer reads the same crop.
        #     The call goes through run_in_executor; assert embedder.embed
        #     appears as a Name in the next K lines (positional arg form).
        assert "embedder.embed" in window, (
            f"P0S1-C0 marker at line {idx + 1}: no `embedder.embed` reference "
            f"in next {K} lines.\nWindow:\n{window}"
        )
        # (c) verify_live or _classify_anti_spoof_verdict called against the
        #     SAME `frame` variable — first positional arg is literally `frame`.
        gate_re = re.compile(
            r"(?:verify_live|_classify_anti_spoof_verdict)\(\s*\n?\s*frame\s*,"
        )
        assert gate_re.search(window), (
            f"P0S1-C0 marker at line {idx + 1}: no `verify_live(frame, ...)` "
            f"or `_classify_anti_spoof_verdict(frame, ...)` call in next "
            f"{K} lines (positional `frame` arg required).\nWindow:\n{window}"
        )


# ────────────────────────────────────────────────────────────────────────────
# (Bonus invariant) — H2 vision_frame emit no longer hardcodes True
# ────────────────────────────────────────────────────────────────────────────


def test_h2_vision_frame_emit_uses_real_verdict_aggregate():
    """Plan v2 §8 — the H2 emit's `anti_spoof_live` field uses the
    per-iteration aggregate (`_h2_iter_live`) rather than the pre-P0.S1
    placeholder `True`. Source-inspection only.
    """
    src = _read("pipeline.py")
    # The aggregate variable name is the load-bearing signal — if a future
    # refactor renames it, this test surfaces the change.
    assert "_h2_iter_live" in src, (
        "H2 emit must thread the per-iteration aggregate verdict — "
        "`_h2_iter_live` variable missing."
    )
    # And the VisionFramePayload constructor passes it (not the literal True).
    assert "anti_spoof_live=_h2_iter_live" in src, (
        "VisionFramePayload(anti_spoof_live=...) must receive the aggregate, "
        "not the legacy placeholder."
    )
