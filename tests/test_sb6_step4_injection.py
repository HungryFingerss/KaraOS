"""SB.6 Step 4 — pipeline injection anchors (visual_query → object_context).

Step 4 wires the Step-2 object-detection channel into the live conversation_turn:
on a ``visual_query`` intent it pulls the freshest camera frame, calls
``detect_objects``, and fills the EXISTING ``object_context`` value (already
threaded into the brain's render block). The load-bearing correctness is the
architect-D3 hedge contract — the ``source == "none"`` split must surface the
hedge (NOT drop it) so the §3.4-step-5 safety path actually fires.

The behavioral half (``object_context_from_result``) is tested by importing the
light ``core.object_detection`` module directly. The gating half lives inside
the ~9k-line ``pipeline.py::conversation_turn``; importing pipeline is heavy and
DLL-prone on the dev box, so the gating matrix is verified by source-inspection
(the Session-78 ``test_voice_bootstrap_replenishment`` precedent).
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

from pathlib import Path

import pytest

import core.object_detection as od
from core import config

_PIPELINE_SRC = (
    Path(__file__).resolve().parent.parent / "pipeline.py"
).read_text(encoding="utf-8")


# ── object_context_from_result: the architect-D3 hedge/confident/None split ───


def test_confident_florence_result_frames_camera_view():
    # source != "none" + non-empty text → confident "camera shows" directive.
    ctx = od.object_context_from_result(od.ObjectResult("a red mug", 0.92, "florence_local"))
    assert ctx is not None
    assert "a red mug" in ctx
    assert "<<<WHAT THE CAMERA SEES>>>" in ctx
    assert "currently shows" in ctx
    # The confident branch must NOT carry the hedge's "do not guess" language.
    assert "Do NOT name or guess" not in ctx


def test_confident_cloud_result_frames_camera_view():
    # The qwen_cloud tier is also a confident source — same confident framing.
    ctx = od.object_context_from_result(od.ObjectResult("a blue water bottle", 1.0, "qwen_cloud"))
    assert ctx is not None
    assert "a blue water bottle" in ctx
    assert "currently shows" in ctx


def test_low_confidence_hedge_is_surfaced_not_dropped():
    # ARCHITECT D3 — the hedge case is source == "none" WITH non-empty text.
    # object_context MUST carry the hedge string (NOT None); dropping it would
    # let the 70B fabricate a confident object on an unclear frame.
    hedge = config.OBJECT_DETECT_HEDGE_TEXT
    ctx = od.object_context_from_result(od.ObjectResult(hedge, 0.10, "none"))
    assert ctx is not None  # the load-bearing assertion — never None for a hedge
    assert hedge in ctx
    assert "<<<WHAT THE CAMERA SEES>>>" in ctx
    assert "Do NOT name or guess" in ctx  # forbids guessing a specific object
    # The hedge directive must NOT masquerade as a confident detection.
    assert "currently shows" not in ctx


def test_empty_text_result_leaves_context_none():
    # ARCHITECT-required graceful degrade: empty text + source "none" means
    # "no detection possible" (frame absent / capability disabled / no result)
    # → object_context stays None and the 70B answers from context.
    assert od.object_context_from_result(od.ObjectResult("", 0.0, "none")) is None


def test_confident_and_hedge_branches_are_distinct():
    # The two non-empty branches produce genuinely different directives so the
    # source split is observable end-to-end, not a cosmetic difference.
    confident = od.object_context_from_result(od.ObjectResult("a knife", 0.9, "florence_local"))
    hedge = od.object_context_from_result(od.ObjectResult(config.OBJECT_DETECT_HEDGE_TEXT, 0.1, "none"))
    assert confident != hedge
    assert "currently shows" in confident and "currently shows" not in hedge


# ── config: master gate default + staleness constant ─────────────────────────


def test_master_gate_defaults_off():
    # Default OFF until the §3.6 Jetson benchmark validates Florence accuracy.
    assert config.OBJECT_DETECTION_ENABLED is False


def test_frame_staleness_constant_present_and_positive():
    assert isinstance(config.OBJECT_DETECT_FRAME_STALENESS_SECS, (int, float))
    assert config.OBJECT_DETECT_FRAME_STALENESS_SECS > 0


# ── pipeline gating matrix (source-inspection of conversation_turn) ───────────


def _injection_block() -> str:
    """The SB.6 Step-4 injection block from conversation_turn (text window)."""
    anchor = "if config.OBJECT_DETECTION_ENABLED:"
    start = _PIPELINE_SRC.index(anchor)
    # The whole block ends at the existing object_context=None comment region;
    # a generous window captures the classify + detect + fill lines.
    return _PIPELINE_SRC[start : start + 1200]


def test_injection_imports_object_detection_channel():
    assert "import core.object_detection as od" in _PIPELINE_SRC


def test_whole_block_gated_on_master_enable():
    # Case 5: OBJECT_DETECTION_ENABLED=False → neither classify nor detect fires.
    block = _injection_block()
    # Everything (classify + detect) sits AFTER the enable guard.
    enable_idx = block.index("if config.OBJECT_DETECTION_ENABLED:")
    assert block.index("_classify_intent_cached(") > enable_idx
    assert block.index("od.detect_objects(") > enable_idx


def test_detect_gated_on_visual_query_intent():
    # Cases 1+2: detect_objects only fires inside the visual_query branch — so a
    # non-visual intent never calls Florence and object_context stays None.
    block = _injection_block()
    vq_idx = block.index('"visual_query"')
    classify_idx = block.index("_classify_intent_cached(")
    detect_idx = block.index("od.detect_objects(")
    # classify happens first, then the visual_query check, then the detect.
    assert classify_idx < vq_idx < detect_idx


def test_frame_pulled_fresh_with_config_staleness():
    block = _injection_block()
    assert "peek_frame_if_fresh(" in block
    assert "OBJECT_DETECT_FRAME_STALENESS_SECS" in block
    assert "time.monotonic()" in block


def test_object_context_filled_from_helper():
    block = _injection_block()
    # The fill routes through the contract-faithful helper (the hedge/confident
    # split), not an inline branch that could drift from the D3 contract.
    assert "object_context = od.object_context_from_result(" in block


def test_detect_objects_receives_the_pulled_frame_and_user_text():
    block = _injection_block()
    # The detect call must consume the fresh frame + the turn's user text.
    assert "od.detect_objects(_vq_frame, text)" in block
