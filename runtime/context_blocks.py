"""runtime/context_blocks.py — Multispeaker transcript + scene-candidate count + zone geometry (pure; scene-block render/cache defers to SP-5).

Extracted VERBATIM from pipeline.py (P1.A1 SP-4 — pure leaves).
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

from core.brain_agent import _infer_location_zone as _brain_infer_zone

from core.config import VOICE_ROUTING_FACE_STALE_SECS


def _infer_zone(bbox: tuple, frame_w: int, frame_h: int) -> str:
    """Map a face bounding box to a zone label using the shared brain_agent helper."""
    x1, y1, x2, y2 = bbox
    cx = (x1 + x2) / 2 / max(frame_w, 1)
    cy = (y1 + y2) / 2 / max(frame_h, 1)
    return _brain_infer_zone(cx, cy)


def _format_multispeaker_transcript(
    named_pairs: "list[tuple[str | None, str]]",
) -> "tuple[str, str, list[str]]":
    """Phase 3B.4 — format a multi-speaker transcript for the brain.

    ``named_pairs`` is a list of ``(name_or_None, transcript)`` tuples in
    diarize order. ``name=None`` means the span didn't match the voice
    gallery — gets assigned ``unknown_1`` / ``unknown_2`` / ... in the
    order it appeared. Numbering is PER-UTTERANCE; no cross-turn state.

    Returns ``(brain_text, log_preview, labels)``:
      - ``brain_text``  — string injected into the user message.
          N=2 preserves legacy `[Name1]: text\\n[Name2]: text` format.
          N≥3 uses a `[N voices simultaneously]\\n{Name}: {text}\\n...`
          block — more readable with 3+ speakers than slash/newline
          mixing, and the header names exact count so brain sees the
          multi-speaker signal prominently.
      - ``log_preview`` — single-line slash-separated for ``[STT]`` log.
      - ``labels``      — list of resolved names (including ``unknown_N``)
          in order. Drives the voice_state "multi_speaker_speakers"
          field that downstream observability reads.

    Returns ``("", "", [])`` if fewer than 2 surviving transcripts —
    caller should treat single-speaker as the normal path.
    """
    if len(named_pairs) < 2:
        return "", "", []
    labels: list[str] = []
    unknown_i = 0
    for name, _ in named_pairs:
        if not name or name == "unknown":
            unknown_i += 1
            labels.append(f"unknown_{unknown_i}")
        else:
            labels.append(name)
    texts = [t for _, t in named_pairs]
    n = len(named_pairs)
    preview = " / ".join(
        f"{name}: \"{t[:60]}\"" for name, t in zip(labels, texts)
    )
    if n == 2:
        brain_text = "\n".join(
            f"[{name}]: {t}" for name, t in zip(labels, texts)
        )
    else:
        brain_text = (
            f"[{n} voices simultaneously]\n"
            + "\n".join(f"{name}: {t}" for name, t in zip(labels, texts))
        )
    return brain_text, preview, labels


def _count_scene_candidates(
    persons_in_frame: dict,
    unrecognized_tracks: dict,
    now: float,
    exclude: str | None = None,
) -> int:
    """Count how many distinct people are plausibly in the scene (excluding `exclude`)."""
    known = sum(
        1 for pid, info in persons_in_frame.items()
        if pid != exclude and now - info.get("last_recognized_at", 0) < VOICE_ROUTING_FACE_STALE_SECS
    )
    unrec = sum(
        1 for ts in unrecognized_tracks.values()
        if now - ts < VOICE_ROUTING_FACE_STALE_SECS
    )
    return known + unrec
