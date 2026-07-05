"""100% coverage for core.emotion — per-person emotion detector over a shared
HuggingFace pipeline. The only external boundary is the transformers pipeline,
mocked here at sys.modules (load path) or as an injected fake callable in the
module-level singleton (runtime paths). Part of the coverage-to-100 campaign
(see COVERAGE.md)."""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

import sys
import time
import types

import pytest

import core.emotion as emotion

@pytest.fixture(autouse=True)
def _isolate_emotion_globals():
    """Save/restore the module-level singleton + config flag around each test so
    the shared-pipeline state never leaks between tests (or into the full suite)."""
    saved_pipeline = emotion._shared_pipeline
    saved_ready = emotion._shared_pipeline_ready
    saved_enabled = emotion.EMOTION_ENABLED
    yield
    emotion._shared_pipeline = saved_pipeline
    emotion._shared_pipeline_ready = saved_ready
    emotion.EMOTION_ENABLED = saved_enabled

# ── _get_pipeline ─────────────────────────────────────────────────────────────

def test_get_pipeline_returns_cached_when_ready():
    # ready flag already set -> early return of the cached singleton (no reload)
    sentinel = object()
    emotion._shared_pipeline = sentinel
    emotion._shared_pipeline_ready = True
    assert emotion._get_pipeline() is sentinel

def test_get_pipeline_disabled_returns_none():
    # EMOTION_ENABLED=False -> line 70 returns None, but the ready flag flips True
    emotion._shared_pipeline = None
    emotion._shared_pipeline_ready = False
    emotion.EMOTION_ENABLED = False
    assert emotion._get_pipeline() is None
    assert emotion._shared_pipeline_ready is True

def test_get_pipeline_successful_load_caches_and_prints(monkeypatch, capsys):
    # transformers.pipeline loads cleanly -> success print (81) + cached return (82)
    fake_transformers = types.ModuleType("transformers")
    fake_pipe = object()

    def _make(*args, **kwargs):
        return fake_pipe

    fake_transformers.pipeline = _make
    monkeypatch.setitem(sys.modules, "transformers", fake_transformers)

    emotion._shared_pipeline = None
    emotion._shared_pipeline_ready = False
    emotion.EMOTION_ENABLED = True

    assert emotion._get_pipeline() is fake_pipe
    assert emotion._shared_pipeline is fake_pipe
    assert "loaded on CPU" in capsys.readouterr().out

def test_get_pipeline_load_failure_returns_none(monkeypatch, capsys):
    # transformers.pipeline raises during load -> except block (83-85) prints + None
    fake_transformers = types.ModuleType("transformers")

    def _boom(*args, **kwargs):
        raise RuntimeError("model unavailable")

    fake_transformers.pipeline = _boom
    monkeypatch.setitem(sys.modules, "transformers", fake_transformers)

    emotion._shared_pipeline = None
    emotion._shared_pipeline_ready = False
    emotion.EMOTION_ENABLED = True

    assert emotion._get_pipeline() is None
    assert "Model load failed" in capsys.readouterr().out

# ── EmotionAgent._ensure_loaded ───────────────────────────────────────────────

def test_ensure_loaded_true_when_pipeline_available():
    emotion._shared_pipeline = object()  # truthy fake pipeline
    emotion._shared_pipeline_ready = True
    assert emotion.EmotionAgent()._ensure_loaded() is True

def test_ensure_loaded_false_when_pipeline_none():
    emotion._shared_pipeline = None
    emotion._shared_pipeline_ready = True
    assert emotion.EmotionAgent()._ensure_loaded() is False

# ── EmotionAgent.process_turn ─────────────────────────────────────────────────

def test_process_turn_short_text_returns_none():
    # fewer than 5 words -> guard short-circuits before any pipeline call
    label, score = emotion.EmotionAgent().process_turn("too short here")
    assert label is None and score == 0.0

def test_process_turn_pipeline_unavailable_returns_none():
    # pipeline is None -> line 124
    emotion._shared_pipeline = None
    emotion._shared_pipeline_ready = True
    label, score = emotion.EmotionAgent().process_turn("this has more than five words here")
    assert label is None and score == 0.0

def test_process_turn_empty_results_returns_none():
    # results is falsy ([]) -> line 128 via the first `not results` clause
    emotion._shared_pipeline = lambda text: []
    emotion._shared_pipeline_ready = True
    label, score = emotion.EmotionAgent().process_turn("plenty of words to pass the gate")
    assert label is None and score == 0.0

def test_process_turn_empty_first_result_returns_none():
    # results[0] is falsy ([[]]) -> line 128 via the `not results[0]` clause
    emotion._shared_pipeline = lambda text: [[]]
    emotion._shared_pipeline_ready = True
    label, score = emotion.EmotionAgent().process_turn("plenty of words to pass the gate")
    assert label is None and score == 0.0

def test_process_turn_significant_emotion_increments_consecutive():
    # valid significant result above EMOTION_MIN_SCORE (0.40) -> counter climbs
    emotion._shared_pipeline = lambda text: [[{"label": "Sadness", "score": 0.82}]]
    emotion._shared_pipeline_ready = True
    agent = emotion.EmotionAgent()

    label, score = agent.process_turn("I am really tired of all this")
    assert label == "sadness"            # top label lowercased
    assert score == pytest.approx(0.82)
    assert agent._consecutive_non_neutral == 1
    assert len(agent._window) == 1

    agent.process_turn("still very much done with everything today")
    assert agent._consecutive_non_neutral == 2  # accumulates across turns

def test_process_turn_neutral_resets_consecutive():
    # neutral (or below-threshold) label -> else branch zeroes the counter
    emotion._shared_pipeline = lambda text: [[{"label": "neutral", "score": 0.99}]]
    emotion._shared_pipeline_ready = True
    agent = emotion.EmotionAgent()
    agent._consecutive_non_neutral = 3  # pretend a prior streak

    label, score = agent.process_turn("the weather report for today looks fine")
    assert label == "neutral"
    assert score == pytest.approx(0.99)
    assert agent._consecutive_non_neutral == 0

def test_process_turn_inference_error_returns_none(capsys):
    # pipeline call raises mid-inference -> except block (138-140) prints + None
    def _boom(text):
        raise RuntimeError("inference boom")

    emotion._shared_pipeline = _boom
    emotion._shared_pipeline_ready = True
    label, score = emotion.EmotionAgent().process_turn("enough words to pass the gate here")
    assert label is None and score == 0.0
    assert "Inference error" in capsys.readouterr().out

# ── EmotionAgent.get_dominant_emotion ─────────────────────────────────────────

def test_get_dominant_emotion_empty_window():
    assert emotion.EmotionAgent().get_dominant_emotion() == (None, 0.0)

def test_get_dominant_emotion_aggregates_and_expires_ttl():
    agent = emotion.EmotionAgent()
    now = time.time()
    agent._window.append(("joy", 0.99, now - 200))  # TTL-expired (>90s) -> skipped
    agent._window.append(("fear", 0.30, now))       # below EMOTION_MIN_SCORE -> skipped
    agent._window.append(("sadness", 0.5, now))
    agent._window.append(("sadness", 0.7, now))
    agent._window.append(("anger", 0.9, now))       # single entry, lower total than sadness
    label, score = agent.get_dominant_emotion()
    assert label == "sadness"               # summed 1.2 beats anger's 0.9
    assert score == pytest.approx(0.6)      # mean of [0.5, 0.7]

def test_get_dominant_emotion_all_entries_filtered_returns_none():
    # window has only stale/weak entries -> totals empty -> (None, 0.0)
    agent = emotion.EmotionAgent()
    now = time.time()
    agent._window.append(("fear", 0.10, now))       # below threshold
    agent._window.append(("joy", 0.95, now - 500))  # TTL-expired
    assert agent.get_dominant_emotion() == (None, 0.0)

# ── EmotionAgent.get_context_string ───────────────────────────────────────────

def test_get_context_string_none_when_neutral():
    assert emotion.EmotionAgent().get_context_string() is None

def test_get_context_string_formats_dominant_emotion():
    agent = emotion.EmotionAgent()
    agent._window.append(("sadness", 0.82, time.time()))
    assert agent.get_context_string() == "CURRENT EMOTIONAL TONE: sad/down (82%)"

# ── EmotionAgent.should_store_as_fact ─────────────────────────────────────────

def test_should_store_as_fact_below_threshold():
    agent = emotion.EmotionAgent()
    agent._consecutive_non_neutral = 1
    assert agent.should_store_as_fact() is False

def test_should_store_as_fact_at_threshold():
    agent = emotion.EmotionAgent()
    agent._consecutive_non_neutral = 2
    assert agent.should_store_as_fact() is True

# ── EmotionAgent.get_fact_value ───────────────────────────────────────────────

def test_get_fact_value_none_when_neutral():
    assert emotion.EmotionAgent().get_fact_value() is None

def test_get_fact_value_formats_dominant_emotion():
    agent = emotion.EmotionAgent()
    agent._window.append(("anger", 0.9, time.time()))
    assert agent.get_fact_value() == "frustrated/angry (detected with 90% confidence)"

# ── EmotionAgent.reset ────────────────────────────────────────────────────────

def test_reset_clears_window_and_counter():
    agent = emotion.EmotionAgent()
    agent._window.append(("joy", 0.9, time.time()))
    agent._consecutive_non_neutral = 3
    agent.reset()
    assert len(agent._window) == 0
    assert agent._consecutive_non_neutral == 0
