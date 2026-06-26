"""SB.6 Step 2 — object-detection channel anchors (Florence-2 STUBBED).

Plan v1 §0/§7: the dev-box suite proves the WIRING (intent → channel → hedge →
cloud-gate → pool-registration) with Florence-2 stubbed via a monkeypatched
``hw.run_heavy``. The real capability is the §3.6 Jetson benchmark gate.

Anchors here cover Step-2 scope ONLY: the ``detect_objects`` channel, the
florence_detect pool registration + supply-chain lock, the consent-gated cloud
tier, the hedge. (describe_frame deletion = Step 5; the SB.5 memory extension =
Step 6 — NOT exercised here.)
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import concurrent.futures
import inspect

import numpy as np
import pytest

import core.heavy_worker as hw
import core.object_detection as od
from core import config


@pytest.fixture
def frame() -> "np.ndarray":
    return np.zeros((480, 640, 3), dtype=np.uint8)


@pytest.fixture(autouse=True)
def _enable_object_detection(monkeypatch):
    # Default-on master gate for the routing/hedge/cloud anchors; the disabled
    # anchor flips it off explicitly.
    monkeypatch.setattr(config, "OBJECT_DETECTION_ENABLED", True)
    monkeypatch.setattr(config, "OBJECT_DETECT_CONFIDENCE_MIN", 0.45)


def _stub_run_heavy(monkeypatch, return_value=None, capture=None):
    async def fake_run_heavy(task_name, fn, *args, **kwargs):
        if capture is not None:
            capture["task_name"] = task_name
            capture["fn"] = fn
            capture["args"] = args
        if isinstance(return_value, Exception):
            raise return_value
        return return_value

    monkeypatch.setattr(hw, "run_heavy", fake_run_heavy)


# ── Intent routing: right task token per question shape ──────────────────────


@pytest.mark.parametrize(
    "text,expected_token",
    [
        ("what's in my hand?", "<CAPTION_TO_PHRASE_GROUNDING>"),
        ("what am I holding right now", "<CAPTION_TO_PHRASE_GROUNDING>"),
        ("what is this thing", "<CAPTION_TO_PHRASE_GROUNDING>"),
        ("what do you see in the room", "<MORE_DETAILED_CAPTION>"),
        ("describe the scene please", "<MORE_DETAILED_CAPTION>"),
        ("read this label for me", "<OCR>"),
        ("what does the label say", "<OCR>"),
    ],
)
async def test_routing_selects_task_token_by_question_shape(
    monkeypatch, frame, text, expected_token
):
    capture = {}
    _stub_run_heavy(monkeypatch, return_value=("an object", 0.9), capture=capture)
    await od.detect_objects(frame, text)
    # args = (frame_bytes, shape, dtype_name, task_token, text_input)
    assert capture["task_name"] == "florence_detect"
    assert capture["fn"] is hw.florence_detect_worker
    assert capture["args"][3] == expected_token


async def test_grounding_passes_user_text_as_phrase(monkeypatch, frame):
    capture = {}
    _stub_run_heavy(monkeypatch, return_value=("a charger", 0.9), capture=capture)
    await od.detect_objects(frame, "what's in my hand?")
    # held-object grounding pulls the phrase from user_text (Plan v1 §1).
    assert capture["args"][4] == "what's in my hand?"


async def test_caption_passes_no_text_input(monkeypatch, frame):
    capture = {}
    _stub_run_heavy(monkeypatch, return_value=("a desk", 0.9), capture=capture)
    await od.detect_objects(frame, "what do you see")
    assert capture["args"][4] is None


# ── Injection contract: high-confidence string → ObjectResult ────────────────


async def test_high_confidence_returns_florence_local(monkeypatch, frame):
    _stub_run_heavy(monkeypatch, return_value=("a red mug", 0.92))
    res = await od.detect_objects(frame, "what's in my hand?")
    assert res.source == "florence_local"
    assert res.text == "a red mug"
    assert res.confidence == pytest.approx(0.92)


async def test_disabled_master_gate_returns_empty_none(monkeypatch, frame):
    monkeypatch.setattr(config, "OBJECT_DETECTION_ENABLED", False)
    res = await od.detect_objects(frame, "what's in my hand?")
    assert res.source == "none"
    assert res.text == ""


async def test_no_frame_returns_empty_none():
    res = await od.detect_objects(None, "what's in my hand?")
    assert res.source == "none"
    assert res.text == ""


# ── Hedge: low-confidence → hedge string, NEVER a confident object name ──────


async def test_low_confidence_returns_hedge_not_object_name(monkeypatch, frame):
    monkeypatch.setattr(config, "OBJECT_DETECTION_ALLOW_CLOUD_FRAMES", False)
    _stub_run_heavy(monkeypatch, return_value=("a knife", 0.10))
    res = await od.detect_objects(frame, "what's in my hand?")
    assert res.source == "none"
    assert res.text == config.OBJECT_DETECT_HEDGE_TEXT
    assert "knife" not in res.text  # safety-critical: never the object name


# ── Cloud gate (privacy-critical): no frame leaves the device when consent off ──


async def test_no_cloud_call_when_consent_off(monkeypatch, frame):
    monkeypatch.setattr(config, "OBJECT_DETECTION_ALLOW_CLOUD_FRAMES", False)
    _stub_run_heavy(monkeypatch, return_value=("uncertain", 0.10))
    calls = {"n": 0}

    async def fake_cloud(*a, **k):
        calls["n"] += 1
        return "leaked description"

    monkeypatch.setattr(od, "_detect_objects_cloud", fake_cloud)
    res = await od.detect_objects(frame, "what's in my hand?")
    assert calls["n"] == 0  # NO frame left the device
    assert res.source == "none"


async def test_cloud_escalation_when_consent_on_and_low_conf(monkeypatch, frame):
    monkeypatch.setattr(config, "OBJECT_DETECTION_ALLOW_CLOUD_FRAMES", True)
    _stub_run_heavy(monkeypatch, return_value=("uncertain", 0.10))

    async def fake_cloud(*a, **k):
        return "a blue water bottle"

    monkeypatch.setattr(od, "_detect_objects_cloud", fake_cloud)
    res = await od.detect_objects(frame, "what's in my hand?")
    assert res.source == "qwen_cloud"
    assert res.text == "a blue water bottle"


async def test_no_cloud_escalation_when_high_conf(monkeypatch, frame):
    # High-confidence local result must NOT escalate even with consent ON.
    monkeypatch.setattr(config, "OBJECT_DETECTION_ALLOW_CLOUD_FRAMES", True)
    _stub_run_heavy(monkeypatch, return_value=("a phone", 0.95))
    calls = {"n": 0}

    async def fake_cloud(*a, **k):
        calls["n"] += 1
        return "x"

    monkeypatch.setattr(od, "_detect_objects_cloud", fake_cloud)
    res = await od.detect_objects(frame, "what's in my hand?")
    assert res.source == "florence_local"
    assert calls["n"] == 0


async def test_cloud_tier_defense_in_depth_returns_none_when_consent_off(
    monkeypatch, frame
):
    # Even a DIRECT call to _detect_objects_cloud respects consent (no http).
    monkeypatch.setattr(config, "OBJECT_DETECTION_ALLOW_CLOUD_FRAMES", False)
    posts = {"n": 0}

    async def fake_post(*a, **k):
        posts["n"] += 1
        raise AssertionError("must not post when consent is off")

    monkeypatch.setattr(od._vision_http, "post", fake_post)
    res = await od._detect_objects_cloud(frame, "what is this?")
    assert res is None
    assert posts["n"] == 0


# ── Pool refusal / crash → hedge (not a crash) ───────────────────────────────


async def test_pool_vram_refused_returns_hedge(monkeypatch, frame):
    monkeypatch.setattr(config, "OBJECT_DETECTION_ALLOW_CLOUD_FRAMES", False)
    _stub_run_heavy(monkeypatch, return_value=None)  # VRAM-refused / load-failed
    res = await od.detect_objects(frame, "what's in my hand?")
    assert res.source == "none"
    assert res.text == config.OBJECT_DETECT_HEDGE_TEXT


async def test_subprocess_crash_degrades_to_hedge_not_raise(monkeypatch, frame):
    monkeypatch.setattr(config, "OBJECT_DETECTION_ALLOW_CLOUD_FRAMES", False)
    boom = concurrent.futures.process.BrokenProcessPool("worker died")
    _stub_run_heavy(monkeypatch, return_value=boom)
    res = await od.detect_objects(frame, "what's in my hand?")  # must NOT raise
    assert res.source == "none"
    assert res.text == config.OBJECT_DETECT_HEDGE_TEXT


# ── Pool registration + supply-chain lock (structural, no GPU) ───────────────


def test_florence_detect_registered_in_vram_tables():
    assert "florence_detect" in config.HEAVY_WORKER_VRAM_ESTIMATES_MB
    assert config.HEAVY_WORKER_VRAM_ESTIMATES_MB["florence_detect"] > 0
    assert "florence_detect" in config.VRAM_POOL_PRIORITY
    # lowest priority → last in the list (first to be VRAM-refused → cloud/hedge).
    assert config.VRAM_POOL_PRIORITY[-1] == "florence_detect"


def test_florence_worker_symbols_exist():
    assert hasattr(hw, "florence_detect_worker")
    assert hasattr(hw, "_get_subprocess_florence")


def test_florence_loader_uses_vendored_package_not_trust_remote_code():
    # Supply-chain lock (source-inspection — no GPU): the loader imports from the
    # vendored core._florence2 package and sets trust_remote_code=False.
    src = inspect.getsource(hw._get_subprocess_florence)
    assert "core._florence2" in src
    assert "trust_remote_code=False" in src
    assert "transformers_modules" not in src  # never the hub remote-code path


def test_object_result_is_frozen():
    r = od.ObjectResult("text", 0.9, "florence_local")
    assert (r.text, r.confidence, r.source) == ("text", 0.9, "florence_local")
    with pytest.raises(Exception):
        r.text = "mutated"  # frozen dataclass
