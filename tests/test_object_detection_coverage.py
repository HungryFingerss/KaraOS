# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors
"""100% coverage for core.object_detection._detect_objects_cloud — the
consent-gated Qwen-VL cloud tier (lines 194-235). Real numpy frames; only the
httpx boundary and (one branch) cv2.imencode are mocked. Headless, no network.
Part of the coverage-to-100 campaign (see COVERAGE.md)."""

import numpy as np
import pytest

import core.object_detection as od
from core import config


class _FakeResp:
    """Minimal stand-in for an httpx.Response the cloud path consumes."""

    def __init__(self, content):
        self._content = content

    def raise_for_status(self):
        return None

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}


def _frame(h, w):
    return np.zeros((h, w, 3), dtype=np.uint8)


def _post_returning(content):
    async def _fake_post(url, json=None):
        return _FakeResp(content)

    return _fake_post


@pytest.fixture(autouse=True)
def _consent_on(monkeypatch):
    # Default every test to consent-ON + a set key so we reach the body under
    # test; individual tests override to exercise the early-return guards.
    monkeypatch.setattr(config, "OBJECT_DETECTION_ALLOW_CLOUD_FRAMES", True)
    monkeypatch.setattr(config, "VISION_API_KEY", "test-key")
    yield


async def test_cloud_disabled_returns_none(monkeypatch):
    # Defense-in-depth consent re-check (line 192-193 False path guard).
    monkeypatch.setattr(config, "OBJECT_DETECTION_ALLOW_CLOUD_FRAMES", False)
    assert await od._detect_objects_cloud(_frame(480, 640), "what is this") is None


async def test_empty_api_key_returns_none(monkeypatch):
    # Line 194 True via missing key.
    monkeypatch.setattr(config, "VISION_API_KEY", "")
    assert await od._detect_objects_cloud(_frame(480, 640), "what is this") is None


async def test_none_frame_returns_none():
    # Line 194 True via frame is None (key present).
    assert await od._detect_objects_cloud(None, "what is this") is None


async def test_large_frame_resizes_and_returns_desc(monkeypatch):
    # Line 198 True branch (resize) + successful HTTP + short desc (line 231
    # ternary False) + line 232 truthy return.
    monkeypatch.setattr(od._vision_http, "post", _post_returning("a red mug"))
    out = await od._detect_objects_cloud(_frame(720, 1280), "what is this")
    assert out == "a red mug"


async def test_small_frame_no_resize_returns_desc(monkeypatch):
    # Line 198 False branch (w==640, h==480 → neither exceeds → no resize).
    monkeypatch.setattr(od._vision_http, "post", _post_returning("blue book"))
    out = await od._detect_objects_cloud(_frame(480, 640), "what do you see")
    assert out == "blue book"


async def test_long_desc_truncates_log(monkeypatch):
    # Line 231 ternary True branch (len(desc) > 80 → '…' suffix in the print).
    long_desc = "x" * 100
    monkeypatch.setattr(od._vision_http, "post", _post_returning(long_desc))
    out = await od._detect_objects_cloud(_frame(480, 640), "describe the scene")
    assert out == long_desc


async def test_imencode_failure_returns_none(monkeypatch):
    # Line 201-202 True branch — encoder reports failure → return None.
    monkeypatch.setattr(od.cv2, "imencode", lambda *a, **k: (False, None))
    assert await od._detect_objects_cloud(_frame(480, 640), "what is this") is None


async def test_empty_response_content_returns_none(monkeypatch):
    # Line 232 falsy branch — whitespace content strips to "" → "" or None → None.
    monkeypatch.setattr(od._vision_http, "post", _post_returning("   "))
    assert await od._detect_objects_cloud(_frame(480, 640), "what is this") is None


async def test_http_exception_returns_none(monkeypatch):
    # Line 233-235 except path — post raises → caught → return None.
    async def _boom(url, json=None):
        raise RuntimeError("network down")

    monkeypatch.setattr(od._vision_http, "post", _boom)
    assert await od._detect_objects_cloud(_frame(480, 640), "what is this") is None
