"""
core/emotion.py — Real-time emotion detection for conversation context.

Model: j-hartmann/emotion-english-distilroberta-base (CPU-only)
7 emotions: joy, sadness, anger, fear, disgust, surprise, neutral
~15-25ms per inference, rolling 5-turn window per person, injected into LLM system prompt.

Architecture:
- Module-level shared HuggingFace pipeline loaded once (not per-person).
- EmotionAgent is a lightweight per-person wrapper around the shared pipeline.
  One agent is created per person_id in pipeline.py and kept alive across sessions
  so emotional context persists when someone briefly leaves and returns.
- Rolling window of N turns per person — dominant non-neutral emotion wins.
- 90-second TTL: entries older than EMOTION_WINDOW_TTL_SECS are excluded.
- Temporal storage: after 2+ consecutive non-neutral turns, fact is stored in brain.db
  as current_feeling (is_temporal=True, valid_for_hours=4)

Graceful degradation: if transformers not installed or model unavailable,
all methods return None and the pipeline continues without emotion context.
"""
from __future__ import annotations

import time
from collections import deque

from core.config import (
    EMOTION_ENABLED, EMOTION_WINDOW, EMOTION_MIN_SCORE,
    EMOTION_WINDOW_TTL_SECS,
)

# Emotions we consider "significant" (non-neutral, worth surfacing to LLM)
_SIGNIFICANT_EMOTIONS = frozenset({
    "joy", "sadness", "anger", "fear", "disgust", "surprise"
})

# Human-readable label → LLM-friendly description
_EMOTION_LABELS = {
    "joy":      "positive/joyful",
    "sadness":  "sad/down",
    "anger":    "frustrated/angry",
    "fear":     "anxious/worried",
    "disgust":  "disgusted/averse",
    "surprise": "surprised/curious",
    "neutral":  "neutral",
}

# ── Module-level shared pipeline singleton ────────────────────────────────────
# One HuggingFace pipeline shared across all EmotionAgent instances — avoids
# loading the ~14 MB DistilRoBERTa model N times for N active persons.

_shared_pipeline       = None   # loaded once, reused forever
_shared_pipeline_ready = False  # True once a load attempt has been made


def _get_pipeline():
    """Return the shared HuggingFace pipeline, loading it on first call.

    Thread-safe: GIL protects the double-checked flag assignment for CPython.
    Returns None when EMOTION_ENABLED=False or load fails.
    """
    global _shared_pipeline, _shared_pipeline_ready
    if _shared_pipeline_ready:
        return _shared_pipeline
    _shared_pipeline_ready = True
    if not EMOTION_ENABLED:
        return None
    try:
        import logging as _logging
        _logging.getLogger("transformers").setLevel(_logging.ERROR)
        from transformers import pipeline as hf_pipeline
        _shared_pipeline = hf_pipeline(
            "text-classification",
            model="j-hartmann/emotion-english-distilroberta-base",
            top_k=1,
            device=-1,    # CPU — leaves GPU free for AdaFace + ONNX
        )
        print("[EmotionAgent] j-hartmann/emotion-english-distilroberta-base loaded on CPU (shared)")
        return _shared_pipeline
    except Exception as e:
        print(f"[EmotionAgent] Model load failed (emotion detection disabled): {e}")
        return None


class EmotionAgent:
    """Per-person emotion detector with rolling window aggregation.

    Instantiate once per person_id.  Keep the instance alive across sessions
    so the emotional context persists when someone briefly leaves and returns.
    The 90-second TTL in get_dominant_emotion() automatically expires stale entries.

    Usage:
        agent = EmotionAgent()
        label, score = agent.process_turn("I'm really tired of this")
        # → ("sadness", 0.72) or (None, 0.0) if neutral/below threshold

        context_str = agent.get_context_string()
        # → "CURRENT EMOTIONAL TONE: sad/down (72%)" or None
    """

    def __init__(self) -> None:
        # Each entry: (emotion_label, score, timestamp)
        self._window: deque[tuple[str, float, float]] = deque(maxlen=EMOTION_WINDOW)
        self._consecutive_non_neutral = 0  # for temporal fact storage threshold

    def _ensure_loaded(self) -> bool:
        """Pre-warm the shared pipeline. Call once from executor at startup."""
        return _get_pipeline() is not None

    def process_turn(self, text: str) -> tuple[str | None, float]:
        """Run emotion classification on a single turn text.

        Returns (emotion_label, score) for the top prediction, or (None, 0.0)
        when the model is unavailable or text is too short.
        The result is also appended to the rolling window with a timestamp.
        """
        if not text or len(text.split()) < 5:
            return None, 0.0
        pipeline = _get_pipeline()
        if pipeline is None:
            return None, 0.0
        try:
            results = pipeline(text[:512])
            if not results or not results[0]:
                return None, 0.0
            top   = results[0][0]
            label = top["label"].lower()
            score = float(top["score"])
            self._window.append((label, score, time.time()))
            if label in _SIGNIFICANT_EMOTIONS and score >= EMOTION_MIN_SCORE:
                self._consecutive_non_neutral += 1
            else:
                self._consecutive_non_neutral = 0
            return label, score
        except Exception as e:
            print(f"[EmotionAgent] Inference error: {e}")
            return None, 0.0

    def get_dominant_emotion(self) -> tuple[str | None, float]:
        """Return the dominant non-neutral emotion from the rolling window.

        Only considers entries within EMOTION_WINDOW_TTL_SECS (90 seconds).
        Sums scores per emotion label across the valid window entries.
        Returns (label, mean_score) for the winner, or (None, 0.0).
        """
        if not self._window:
            return None, 0.0

        cutoff = time.time() - EMOTION_WINDOW_TTL_SECS
        totals: dict[str, list[float]] = {}
        for label, score, ts in self._window:
            if ts < cutoff:
                continue   # entry too old — TTL expired
            if label in _SIGNIFICANT_EMOTIONS and score >= EMOTION_MIN_SCORE:
                totals.setdefault(label, []).append(score)

        if not totals:
            return None, 0.0

        best_label = max(totals, key=lambda k: sum(totals[k]))
        mean_score = sum(totals[best_label]) / len(totals[best_label])
        return best_label, mean_score

    def get_context_string(self) -> str | None:
        """Return a one-line emotion context string for LLM system prompt injection.

        Returns None when the emotion signal is neutral or too weak to surface.
        Example: "CURRENT EMOTIONAL TONE: sad/down (72%)"
        """
        label, score = self.get_dominant_emotion()
        if label is None:
            return None
        human = _EMOTION_LABELS.get(label, label)
        return f"CURRENT EMOTIONAL TONE: {human} ({score:.0%})"

    def should_store_as_fact(self) -> bool:
        """Return True when emotion has been persistent enough to store as a temporal fact.

        Threshold: 2+ consecutive non-neutral turns with a consistent dominant emotion.
        Prevents single-turn spikes from polluting the knowledge base.
        """
        return self._consecutive_non_neutral >= 2

    def get_fact_value(self) -> str | None:
        """Return the current dominant emotion as a storable fact value, or None."""
        label, score = self.get_dominant_emotion()
        if label is None:
            return None
        return f"{_EMOTION_LABELS.get(label, label)} (detected with {score:.0%} confidence)"

    def reset(self) -> None:
        """Clear the rolling window — call at session start if a hard reset is needed."""
        self._window.clear()
        self._consecutive_non_neutral = 0
