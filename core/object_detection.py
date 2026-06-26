"""Object-detection visual-query channel (SB.6 Step 2).

A self-contained channel module — NOT bolted into face-only ``core/vision.py``,
NOT routed through the identity reconciler (an ``ObjectClaim`` with no pid would
structurally read as a ``new_stranger`` candidate to the 3 guarded emitters,
risking the #128 tripwire). It owns BOTH detection tiers + the hedge:

- ``detect_objects(frame, user_text) -> ObjectResult`` — the public async entry.
  Picks a Florence-2 task token by question shape, dispatches the on-device
  Florence-2 tier via the 5th heavy-worker pool, escalates to the consent-gated
  Qwen-VL cloud tier ONLY when (low-confidence OR pool unavailable) AND consent
  is ON, and hedges below ``OBJECT_DETECT_CONFIDENCE_MIN`` (never a confident
  object name on an ambiguous frame — the safety-critical case).
- On-device tier: ``core/heavy_worker.py::florence_detect_worker`` via
  ``run_heavy("florence_detect", ...)`` — VENDORED Florence-2 (no
  trust_remote_code), query-triggered (lazy pool), VRAM-guarded (a VRAM-refused
  spawn returns None → the P0.R6 None-fallback → cloud-or-hedge).
- Cloud tier (D3 — rebuilt fresh, NOT the deleted ``describe_frame``):
  ``_detect_objects_cloud`` calls the configured Qwen-VL leaf behind the
  ``OBJECT_DETECTION_ALLOW_CLOUD_FRAMES`` consent gate (default OFF — a frame
  leaving the device is a privacy event).

Per Plan v1 §0 the dev-box suite proves the WIRING (Florence-2 stubbed); the
real capability is the §3.6 Jetson benchmark gate (a Jagan hardware action item).
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
from typing import TYPE_CHECKING

import cv2
import httpx

import core.heavy_worker as hw
from core import config

if TYPE_CHECKING:  # numpy is available at runtime; keep the import lean.
    import numpy as np

# Dedicated async HTTP client for the Qwen-VL cloud tier. The cloud tier moved
# OUT of brain.py per D3, so this module owns its own client (mirrors the
# brain._chat_http Bearer-auth shape).
_vision_http = httpx.AsyncClient(
    headers={"Authorization": f"Bearer {config.VISION_API_KEY}"},
    timeout=20.0,
)


@dataclass(frozen=True, slots=True)
class ObjectResult:
    """The ``detect_objects`` return.

    - ``text``: the human phrase for ``object_context`` (or the hedge string).
    - ``confidence``: drives the hedge (compared to ``OBJECT_DETECT_CONFIDENCE_MIN``).
    - ``source``: ``"florence_local"`` | ``"qwen_cloud"`` | ``"none"``.

    An empty ``text`` with ``source == "none"`` means "no detection possible"
    (frame absent / capability disabled) — the injection layer leaves
    ``object_context`` None and the 70B answers from context (graceful degrade).
    """

    text: str
    confidence: float
    source: str


def _select_task(user_text: str) -> "tuple[str, str | None]":
    """Pick the Florence-2 task token by question shape (Plan v1 §1).

    OCR first (most specific: "read this / what does the label say"), then
    held-object grounding ("what's in my hand / what am I holding / what is
    this" → ``<CAPTION_TO_PHRASE_GROUNDING>``; catch #2 — NOT
    ``<OPEN_VOCABULARY_DETECTION>``), else the scene caption (the default: "what
    do you see / what's around / describe the scene").
    """
    lt = (user_text or "").lower()
    if any(kw in lt for kw in config.OBJECT_DETECT_OCR_KEYWORDS):
        return ("<OCR>", None)
    if any(kw in lt for kw in config.OBJECT_DETECT_GROUNDING_KEYWORDS):
        # The grounded phrase is pulled from user_text (Plan v1 §1). The §3.6
        # Jetson benchmark validates held-object grounding quality on real
        # KaraOS frames — the dev-box suite only proves the right token fires.
        return ("<CAPTION_TO_PHRASE_GROUNDING>", (user_text or "").strip())
    return ("<MORE_DETAILED_CAPTION>", None)


async def detect_objects(frame: "np.ndarray | None", user_text: str) -> ObjectResult:
    """Public async entry — resolve a visual query to an ``ObjectResult``.

    Never raises — a subprocess crash, pool refusal, or detection failure
    degrades to cloud-or-hedge so the conversation turn never breaks (Plan v1
    §1 "never crash").
    """
    if not config.OBJECT_DETECTION_ENABLED or frame is None:
        return ObjectResult("", 0.0, "none")

    task_token, text_input = _select_task(user_text)

    worker_result = None
    try:
        worker_result = await hw.run_heavy(
            "florence_detect",
            hw.florence_detect_worker,
            frame.tobytes(),
            tuple(frame.shape),
            frame.dtype.name,
            task_token,
            text_input,
        )
    except Exception as _e:
        # Subprocess crash (BrokenProcessPool) / dispatch failure → degrade, do
        # NOT crash the turn. Fall through to cloud-or-hedge.
        print(f"[ObjectDetection] florence dispatch failed: {type(_e).__name__}: {_e}")
        worker_result = None

    local_conf = 0.0
    if worker_result is not None:
        text, conf = worker_result
        if text and conf >= config.OBJECT_DETECT_CONFIDENCE_MIN:
            return ObjectResult(text, conf, "florence_local")
        local_conf = conf  # ran but low-confidence → cloud-or-hedge below

    # Escalation fires ONLY when consent is ON (privacy-critical: with consent
    # OFF no frame ever leaves the device).
    if config.OBJECT_DETECTION_ALLOW_CLOUD_FRAMES:
        cloud_text = await _detect_objects_cloud(frame, user_text)
        if cloud_text:
            return ObjectResult(cloud_text, 1.0, "qwen_cloud")

    # Hedge — never a confident object name on a low-confidence / unavailable
    # detection (the safety-critical case; mirrors Bug-N sparse-memory).
    return ObjectResult(config.OBJECT_DETECT_HEDGE_TEXT, local_conf, "none")


def object_context_from_result(result: ObjectResult) -> "str | None":
    """Map an ``ObjectResult`` onto the ``object_context`` prompt value (SB.6 Step 4).

    The contract is the load-bearing part (architect D3): the ``text``/``source``
    split decides which of three branches fires —

    - **empty ``text``** → no detection possible (frame absent / capability
      disabled / genuine no-result). Return None so the brain's render block
      stays silent and the 70B answers from context (graceful degrade).
    - **non-empty ``text``, ``source != "none"``** → a confident detection
      (florence_local / qwen_cloud). Frame the camera view so the render block
      phrases the answer naturally.
    - **non-empty ``text``, ``source == "none"``** → the HEDGE string (the
      §3.4-step-5 safety path: low-confidence / pool-unavailable). Surface it
      honestly and forbid guessing a specific object — NEVER drop it (dropping
      the hedge would let the 70B fabricate a confident object name).

    The directive framing lives here because ``object_context`` is rendered RAW
    by ``brain._render_object_context`` (no ``<<<...>>>`` wrapper of its own), so
    whatever we return IS the block the brain reads.
    """
    if not result.text:
        return None
    if result.source != "none":
        return (
            "<<<WHAT THE CAMERA SEES>>>\n"
            "The user asked a question about something visible. The camera "
            f"currently shows: {result.text}\n"
            "Use this to answer their question naturally.\n"
            "<<<END>>>"
        )
    # source == "none" with non-empty text → the hedge string. Surface it
    # honestly; never let the 70B guess a confident object on an unclear frame.
    return (
        "<<<WHAT THE CAMERA SEES>>>\n"
        "The user asked about something visible, but the camera view was not "
        f"clear enough to be sure. Tell them honestly: \"{result.text}\"\n"
        "Do NOT name or guess a specific object.\n"
        "<<<END>>>"
    )


async def _detect_objects_cloud(
    frame: "np.ndarray | None", user_text: str
) -> "str | None":
    """Consent-gated Qwen-VL cloud fallback (D3 — rebuilt fresh, NOT
    ``describe_frame``). 640×480 JPEG, base64, the configured Qwen3-VL leaf.
    Returns None on consent-off / missing key / any failure (graceful degrade).
    """
    # Defense-in-depth: the caller gates on consent, but re-check here so a
    # direct call can NEVER leak a frame without consent.
    if not config.OBJECT_DETECTION_ALLOW_CLOUD_FRAMES:
        return None
    if not config.VISION_API_KEY or frame is None:
        return None
    try:
        h, w = frame.shape[:2]
        if w > 640 or h > 480:
            frame = cv2.resize(frame, (640, 480))
        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        if not ok:
            return None
        b64 = base64.b64encode(buf.tobytes()).decode()
        prompt = (
            "Look at the image and answer the user's question about the visible "
            "objects or what the person is holding. Be brief and specific — name "
            "the object(s) and key colors. If you cannot tell, say so honestly.\n"
            f"User question: {user_text}"
        )
        resp = await asyncio.wait_for(
            _vision_http.post(
                f"{config.VISION_BASE_URL}/chat/completions",
                json={
                    "model": config.VISION_MODEL,
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "image_url",
                             "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                            {"type": "text", "text": prompt},
                        ],
                    }],
                    "max_tokens": 120,
                    "temperature": 0.3,
                },
            ),
            timeout=15.0,
        )
        resp.raise_for_status()
        desc = resp.json()["choices"][0]["message"]["content"].strip()
        print(f"[ObjectDetection] cloud (Qwen-VL): {desc[:80]}{'…' if len(desc) > 80 else ''}")
        return desc or None
    except Exception as e:
        print(f"[ObjectDetection] cloud detection failed: {e}")
        return None
