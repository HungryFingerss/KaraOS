"""test_pipeline_diarize_multispeaker — diarize multispeaker tests (split from test_pipeline.py, P1.A1 SP-1).

Behavior-neutral move: test bodies are verbatim from the original root
test_pipeline.py. `import pipeline` stays lazy inside each test body (stubs are
installed by tests/conftest.py).
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

import asyncio
import sys
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock
import types
import pytest
import numpy as np
import time as _time_mod
import numpy as _np


@pytest.mark.slow
@pytest.mark.models
@pytest.mark.xfail(
    strict=False,
    reason=(
        "P0.0.2 infra debt: torchaudio DLL missing on Windows dev machine; "
        "patch applied at core.voice import time but test imports in "
        "isolation. Remediation: include torchaudio wheel in dev venv. "
        "See tests/test_infra_debt_allowlist.py::INFRA_DEBT_FAILURES."
    ),
)
def test_torchaudio_list_audio_backends_patch_applied_at_import():
    """voice.py must patch list_audio_backends onto torchaudio at module import time.
    Marked slow+models: importing voice.py drags torchaudio + speechbrain into scope.
    Marked xfail per P0.0.2: torchaudio DLL crash on Windows dev — XPASS signals
    the infra debt was resolved (slow CI shows it as notable, not failing)."""
    import torchaudio
    # voice.py is imported as part of the test suite — the patch must already be applied
    assert hasattr(torchaudio, "list_audio_backends"), \
        "torchaudio.list_audio_backends should be patched by voice.py at import time"
    result = torchaudio.list_audio_backends()
    assert isinstance(result, list), "list_audio_backends() must return a list"


@pytest.mark.slow
@pytest.mark.models
@pytest.mark.xfail(
    strict=False,
    reason=(
        "P0.0.2 infra debt: SpeechBrain logger suppression test requires the "
        "real SpeechBrain import chain, which triggers the torchaudio DLL "
        "crash on Windows dev. Remediation: fix torchaudio wheel (unblocks "
        "this + torchaudio test together). See "
        "tests/test_infra_debt_allowlist.py::INFRA_DEBT_FAILURES."
    ),
)
def test_speechbrain_logger_suppressed_at_import():
    """speechbrain logger must be at ERROR level after voice.py is imported.
    Marked slow+models: needs the real speechbrain package and its logger config.
    Marked xfail per P0.0.2: shares the torchaudio DLL root cause."""
    import logging
    sb_logger = logging.getLogger("speechbrain")
    assert sb_logger.level == logging.ERROR, \
        f"speechbrain logger should be ERROR, got level={sb_logger.level}"


async def test_diarize_returns_empty_when_audio_too_short():
    """diarize() must return [] when audio is shorter than DIARIZE_MIN_SECS.

    P0.R6.Y D3 migration: diarize() is async; await the call.
    """
    import numpy as np
    from core.voice import diarize
    from core.config import DIARIZE_MIN_SECS, MIC_SAMPLE_RATE

    short_audio = np.zeros(int(DIARIZE_MIN_SECS * MIC_SAMPLE_RATE) - 1, dtype=np.float32)
    result = await diarize(short_audio, voice_gallery={})
    assert result == [], f"Expected [] for short audio, got {result}"


async def test_diarize_returns_empty_when_embedder_unavailable():
    """diarize() must return [] when the ECAPA embedder is not loaded.

    P0.R6.Y D3 migration: embed() now dispatches to hw.run_heavy; the
    ECAPA-embedder-not-loaded condition is now represented by the worker
    returning None. Patches embed() to return None via AsyncMock.
    """
    import numpy as np
    from unittest.mock import patch, AsyncMock
    import core.voice as _voice_mod
    from core.config import DIARIZE_MIN_SECS, MIC_SAMPLE_RATE

    audio = np.zeros(int(DIARIZE_MIN_SECS * MIC_SAMPLE_RATE) * 2, dtype=np.float32)
    # P0.R6.Y D3: simulate "embedder not loaded" via embed() returning None.
    with patch("core.voice.embed", new=AsyncMock(return_value=None)):
        result = await _voice_mod.diarize(audio, voice_gallery={})
    assert result == []


async def test_diarize_returns_empty_for_single_speaker():
    """diarize() must return [] when all windows have high cosine similarity (one speaker).

    P0.R6.Y D3 migration: async cascade; patch embed via AsyncMock.
    """
    import numpy as np
    from unittest.mock import patch, AsyncMock
    import core.voice as _voice_mod
    from core.config import DIARIZE_MIN_SECS, MIC_SAMPLE_RATE, VOICE_EMBEDDING_DIM

    audio = np.zeros(int(DIARIZE_MIN_SECS * MIC_SAMPLE_RATE) * 2, dtype=np.float32)

    # All windows return the same embedding → similarity = 1.0 everywhere → no boundary
    same_emb = np.ones(VOICE_EMBEDDING_DIM, dtype=np.float32)
    same_emb /= np.linalg.norm(same_emb)

    with patch.object(_voice_mod, "_embedder", object()):
        with patch("core.voice.embed", new=AsyncMock(return_value=same_emb)):
            result = await _voice_mod.diarize(audio, voice_gallery={})

    assert result == [], f"Expected [] for single speaker, got {result}"


@pytest.mark.xfail(
    strict=False,
    reason="requires real core.voice._diarize_ecapa_valley; real module "
           "unavailable on Windows dev due to torchaudio DLL crash (OSError "
           "0xc0000139) — stub returns MagicMock([]) not real cosine-valley output",
)
async def test_diarize_returns_two_segments_on_speaker_change():
    """Legacy ECAPA-valley backend (``_diarize_ecapa_valley``) returns 2
    segments when a clear cosine valley is detected. Session 88 P2 moved
    the public ``diarize()`` to pyannote by default — this test targets
    the ECAPA backend directly since the behavior under test (cosine-
    valley binary split from faked embeddings) is specific to that
    backend. Routing through ``diarize()`` would hit pyannote, which has
    its own segmentation model that ignores our monkeypatched ``embed``.

    P0.R6.Y D3 migration: async cascade; patch embed + identify via AsyncMock.
    """
    import numpy as np
    from unittest.mock import patch, AsyncMock
    import core.voice as _voice_mod
    from core.config import (
        DIARIZE_MIN_SECS, MIC_SAMPLE_RATE, VOICE_EMBEDDING_DIM,
        DIARIZE_CHANGE_THRESH,
    )

    audio = np.zeros(int(DIARIZE_MIN_SECS * MIC_SAMPLE_RATE) * 3, dtype=np.float32)

    # Two clearly distinct speakers: first half returns emb_a, second half returns emb_b
    # (orthogonal → cosine = 0.0 at the boundary, well below DIARIZE_CHANGE_THRESH=0.70)
    emb_a    = np.zeros(VOICE_EMBEDDING_DIM, dtype=np.float32); emb_a[0] = 1.0
    emb_b    = np.zeros(VOICE_EMBEDDING_DIM, dtype=np.float32); emb_b[1] = 1.0
    call_cnt = [0]

    def _fake_embed(seg, sr=MIC_SAMPLE_RATE):
        call_cnt[0] += 1
        # First half of windows → emb_a, second half → emb_b
        return emb_a if call_cnt[0] <= 4 else emb_b

    with patch.object(_voice_mod, "_embedder", object()):
        with patch("core.voice.embed", new=AsyncMock(side_effect=_fake_embed)):
            # identify() calls embed() too — patch identify to avoid recursion
            with patch("core.voice.identify", new=AsyncMock(return_value=(None, 0.0, True))):
                result = await _voice_mod._diarize_ecapa_valley(audio, voice_gallery={})

    assert len(result) == 2, f"Expected 2 segments, got {len(result)}"
    assert result[0]["start_sample"] == 0, "First segment must start at 0"
    assert result[1]["end_sample"] == len(audio), "Second segment must end at audio length"
    assert result[0]["end_sample"] == result[1]["start_sample"], \
        "Segments must be contiguous (no gap or overlap)"


def test_diarize_config_constants_exist():
    """Required diarization constants must be present in config.py."""
    from core.config import (
        DIARIZE_WINDOW_SECS, DIARIZE_HOP_SECS,
        DIARIZE_CHANGE_THRESH, DIARIZE_MIN_SECS,
    )
    assert 0 < DIARIZE_WINDOW_SECS <= 1.0, "DIARIZE_WINDOW_SECS out of expected range"
    assert 0 < DIARIZE_HOP_SECS < DIARIZE_WINDOW_SECS, "DIARIZE_HOP_SECS must be < window"
    assert 0.5 < DIARIZE_CHANGE_THRESH < 1.0, "DIARIZE_CHANGE_THRESH out of expected range"
    assert DIARIZE_MIN_SECS >= 1.0, "DIARIZE_MIN_SECS must be at least 1 second"


def test_pipeline_imports_diarize_constants():
    """pipeline.py must import DIARIZE_MIN_SECS and MIC_SAMPLE_RATE from config."""
    import inspect, pipeline
    src = inspect.getsource(pipeline)
    assert "DIARIZE_MIN_SECS" in src, "DIARIZE_MIN_SECS must be imported in pipeline.py"
    assert "MIC_SAMPLE_RATE" in src, "MIC_SAMPLE_RATE must be imported in pipeline.py"
    assert "voice_mod.diarize" in src, "voice_mod.diarize must be called in pipeline.py"


@pytest.mark.slow
@pytest.mark.models
@pytest.mark.xfail(
    strict=False,
    reason=(
        "P0.0.2 infra debt: pyannote.audio pipeline load fails — patched "
        "io.py not applied in this test's import context. Remediation: "
        "P0.R5 pyannote vendor patch. See "
        "tests/test_infra_debt_allowlist.py::INFRA_DEBT_FAILURES."
    ),
)
async def test_diarize_drops_segments_below_min_segment_secs():
    """P2.4 policy: pyannote segments shorter than DIARIZE_MIN_SEGMENT_SECS
    (0.5s) are dropped entirely — ECAPA is too noisy below this bound AND
    pyannote itself often low-confidences these. A 0.3s segment paired with
    a 1.5s segment must produce exactly one output (the 1.5s one).

    P0.R6.Y D3 migration: async cascade; patch identify via AsyncMock.
    """
    import numpy as np
    from unittest.mock import patch, AsyncMock
    import core.voice as _voice_mod
    from core.config import MIC_SAMPLE_RATE

    audio = np.zeros(3 * MIC_SAMPLE_RATE, dtype=np.float32)   # 3s @ 16k
    # P0.R6.Z D3.b: worker returns list[tuple[float, float, str]] (Q2 (a)
    # serialization). Mock hw.run_heavy directly to skip the subprocess.
    segments_raw = [
        (0.0, 0.3, "SPEAKER_00"),   # too short — drop
        (0.5, 2.0, "SPEAKER_01"),   # 1.5s — keep + attribute
    ]
    with patch("core.heavy_worker.run_heavy", new=AsyncMock(return_value=segments_raw)), \
         patch("core.voice.identify", new=AsyncMock(return_value=(None, 0.0, True))):
        segs = await _voice_mod.diarize(audio, voice_gallery={})
    assert len(segs) == 1, f"expected 1 (0.3s dropped), got {len(segs)}: {segs}"
    assert segs[0]["speaker_label"] == "SPEAKER_01"


@pytest.mark.slow
@pytest.mark.models
@pytest.mark.xfail(
    strict=False,
    reason=(
        "P0.0.2 infra debt: shares pyannote load failure with "
        "test_diarize_drops_segments_below_min_segment_secs. "
        "Remediation: P0.R5 pyannote vendor patch."
    ),
)
async def test_diarize_short_segment_drops_attribution_keeps_label():
    """P2.4 policy: segments in the DIARIZE_MIN_SEGMENT_SECS–DIARIZE_MIN_EMBED_SECS
    band (0.5s–1.0s) are kept in the output — pyannote's segmentation info
    is preserved — but speaker_id is None because ECAPA needs ≥1.0s for a
    reliable embedding. speaker_label still set so downstream can still
    differentiate speakers within the call.

    P0.R6.Y D3 migration: async cascade; patch identify via AsyncMock.
    """
    import numpy as np
    from unittest.mock import patch, AsyncMock
    import core.voice as _voice_mod
    from core.config import MIC_SAMPLE_RATE

    audio = np.zeros(2 * MIC_SAMPLE_RATE, dtype=np.float32)
    # P0.R6.Z D3.b: worker returns list[tuple]; mock hw.run_heavy.
    segments_raw = [
        (0.0, 0.7, "SPEAKER_00"),   # 0.7s — keep, no attribute
    ]
    with patch("core.heavy_worker.run_heavy", new=AsyncMock(return_value=segments_raw)), \
         patch("core.voice.identify", new=AsyncMock(return_value=("p1", 0.9, False))) as mock_identify:
        segs = await _voice_mod.diarize(audio, voice_gallery={"p1": np.ones(192) / (192**0.5)})
    assert len(segs) == 1
    assert segs[0]["speaker_id"] is None, (
        "segment in 0.5-1.0s band must NOT be attributed — ECAPA embedding "
        "below the min-embed threshold is too noisy to trust"
    )
    assert segs[0]["speaker_score"] == 0.0
    assert segs[0]["speaker_label"] == "SPEAKER_00"
    mock_identify.assert_not_called()   # identify() must be skipped for short segs


@pytest.mark.slow
@pytest.mark.models
@pytest.mark.xfail(
    strict=False,
    reason=(
        "P0.0.2 infra debt: shares pyannote load failure with "
        "test_diarize_drops_segments_below_min_segment_secs. "
        "Remediation: P0.R5 pyannote vendor patch."
    ),
)
async def test_diarize_three_speaker_returns_distinct_labels():
    """P2 regression: pyannote's clustering must differentiate ≥3 speakers
    in a single call, with each segment carrying a distinct speaker_label.
    This is the core Phase 2 capability — legacy _diarize_ecapa_valley
    silently fails on 3+ speakers (binary split only).

    P0.R6.Y D3 migration: async cascade; patch identify via AsyncMock.
    """
    import numpy as np
    from unittest.mock import patch, AsyncMock
    import core.voice as _voice_mod
    from core.config import MIC_SAMPLE_RATE

    audio = np.zeros(6 * MIC_SAMPLE_RATE, dtype=np.float32)
    # P0.R6.Z D3.b: worker returns list[tuple]; mock hw.run_heavy.
    segments_raw = [
        (0.0, 2.0, "SPEAKER_00"),
        (2.0, 4.0, "SPEAKER_01"),
        (4.0, 6.0, "SPEAKER_02"),
    ]
    with patch("core.heavy_worker.run_heavy", new=AsyncMock(return_value=segments_raw)), \
         patch("core.voice.identify", new=AsyncMock(return_value=(None, 0.0, True))):
        segs = await _voice_mod.diarize(audio, voice_gallery={})
    assert len(segs) == 3, f"expected 3 segments, got {len(segs)}"
    labels = {s["speaker_label"] for s in segs}
    assert len(labels) == 3, f"expected 3 distinct labels, got {labels}"
    assert labels == {"SPEAKER_00", "SPEAKER_01", "SPEAKER_02"}


@pytest.mark.slow
@pytest.mark.models
@pytest.mark.xfail(
    strict=False,
    reason=(
        "P0.0.2 infra debt: shares pyannote load failure with "
        "test_diarize_drops_segments_below_min_segment_secs. "
        "Remediation: P0.R5 pyannote vendor patch."
    ),
)
async def test_diarize_empty_gallery_segments_still_have_speaker_label():
    """P2 edge case: empty voice_gallery → every segment gets
    speaker_id=None (ECAPA has nothing to match against), but
    speaker_label is still populated from pyannote's clustering so
    downstream multi-speaker transcribe can still separate speakers
    WITHIN the call.

    P0.R6.Y D3 migration: async cascade; patch identify via AsyncMock.
    """
    import numpy as np
    from unittest.mock import patch, AsyncMock
    import core.voice as _voice_mod
    from core.config import MIC_SAMPLE_RATE

    audio = np.zeros(4 * MIC_SAMPLE_RATE, dtype=np.float32)
    # P0.R6.Z D3.b: worker returns list[tuple]; mock hw.run_heavy.
    segments_raw = [
        (0.0, 2.0, "SPEAKER_00"),
        (2.0, 4.0, "SPEAKER_01"),
    ]
    with patch("core.heavy_worker.run_heavy", new=AsyncMock(return_value=segments_raw)), \
         patch("core.voice.identify", new=AsyncMock(return_value=(None, 0.0, True))):
        segs = await _voice_mod.diarize(audio, voice_gallery={})
    assert len(segs) == 2
    assert all(s["speaker_id"] is None for s in segs)
    assert {s["speaker_label"] for s in segs} == {"SPEAKER_00", "SPEAKER_01"}


@pytest.mark.slow
@pytest.mark.models
@pytest.mark.xfail(
    strict=False,
    reason=(
        "P0.0.2 infra debt: shares pyannote load failure with "
        "test_diarize_drops_segments_below_min_segment_secs. "
        "Remediation: P0.R5 pyannote vendor patch."
    ),
)
async def test_diarize_speaker_id_attribution_via_ecapa_gallery():
    """P2 happy path: segments ≥1.0s run ECAPA, attribute via
    voice_gallery match. Mock identify to return a known (pid, score)
    and assert it flows into the output segment. This is the real value-
    add over legacy: we preserve both pyannote's clustering (label) AND
    cross-chunk identity (speaker_id from gallery).

    P0.R6.Y D3 migration: async cascade; patch identify via AsyncMock
    (side_effect sync callable returns from iter — AsyncMock wraps).
    """
    import numpy as np
    from unittest.mock import patch, AsyncMock
    import core.voice as _voice_mod
    from core.config import MIC_SAMPLE_RATE

    audio = np.zeros(3 * MIC_SAMPLE_RATE, dtype=np.float32)
    # P0.R6.Z D3.b: worker returns list[tuple]; mock hw.run_heavy.
    segments_raw = [
        (0.0, 1.5, "SPEAKER_00"),
        (1.5, 3.0, "SPEAKER_01"),
    ]
    # identify returns different tuples on successive calls.
    identify_returns = iter([("jagan_abc", 0.85, False), ("wasim_def", 0.78, False)])
    with patch("core.heavy_worker.run_heavy", new=AsyncMock(return_value=segments_raw)), \
         patch("core.voice.identify", new=AsyncMock(side_effect=lambda *a, **kw: next(identify_returns))):
        segs = await _voice_mod.diarize(audio, voice_gallery={"jagan_abc": np.ones(192)})
    assert segs[0]["speaker_id"] == "jagan_abc"
    assert segs[0]["speaker_score"] == pytest.approx(0.85)
    assert segs[0]["speaker_label"] == "SPEAKER_00"
    assert segs[1]["speaker_id"] == "wasim_def"
    assert segs[1]["speaker_score"] == pytest.approx(0.78)
    assert segs[1]["speaker_label"] == "SPEAKER_01"


def test_pipeline_consumer_handles_n_segment_diarize_output():
    """Session 88 P2 Part B regression guard (reviewer-flagged critical):
    pipeline.py:4478 was previously hardcoded to ``len(_diar) == 2``, which
    meant 3+ speaker utterances silently fell through to single-speaker
    handling — defeating the whole point of swapping in pyannote. Refactor
    moved to ``len(_diar) >= 2`` with span-grouping by speaker_label.

    This test is source-inspection: the exact pre-refactor hardcode must
    be GONE and the new ≥2 generalization must be in its place. Source
    inspection is correct here — building a behavior-level fixture for
    ``run()``'s within-utterance path requires standing up the whole
    pipeline, far more setup than the invariant warrants."""
    import inspect, pipeline
    src = inspect.getsource(pipeline.run)
    # The legacy exactly-2 hardcode must be gone.
    assert "if len(_diar) == 2:" not in src, (
        "Session 88 P2 Part B: the legacy exactly-2-speaker hardcode must be "
        "replaced with N-segment consumption. Reverting to ``== 2`` would "
        "silently swallow 3+ speaker utterances — defeats Phase 2."
    )
    # The new generalization must be present.
    assert "if len(_diar) >= 2:" in src, (
        "Session 88 P2 Part B: N-segment consumer must check ``len(_diar) >= 2``"
    )
    # Span grouping by speaker_label must be present (prevents pyannote's
    # small adjacent same-speaker fragments from blowing up the transcribe
    # budget + producing noisy [Name]: blocks).
    assert "speaker_label" in src, (
        "Session 88 P2 Part B: span grouping must read speaker_label to merge "
        "consecutive same-speaker segments before transcription"
    )
    # The multi-speaker-gate must still require ≥2 non-empty transcripts.
    # Session 3B.4 renamed `_lines` → `_named_pairs` (pushed formatting into
    # `_format_multispeaker_transcript`). Accept either name — the invariant
    # is the count gate, not the variable name.
    assert (
        "if len(_lines) >= 2:" in src
        or "if len(_named_pairs) >= 2:" in src
    ), (
        "multi-speaker block must still gate on ≥2 non-empty transcripts — "
        "single-surviving-span cases must fall through to normal single-"
        "speaker flow"
    )


@pytest.mark.slow
@pytest.mark.models
@pytest.mark.xfail(
    strict=False,
    reason=(
        "P0.0.2 infra debt: shares pyannote load failure with "
        "test_diarize_drops_segments_below_min_segment_secs. "
        "Remediation: P0.R5 pyannote vendor patch."
    ),
)
async def test_diarize_pyannote_error_falls_back_to_ecapa_and_bumps_counter():
    """P2 fail-safe (reviewer's Session 88 observability ask): pyannote
    runtime error with DIARIZATION_FALLBACK_ON_ERROR=True must (1) call
    _diarize_ecapa_valley instead, (2) bump _diarize_fallback_count so
    Phase 5 drift detection can spot pyannote-regression climbing
    fallback rate before it becomes a silent production bug.

    P0.R6.Y D3 migration: async cascade; _diarize_ecapa_valley fallback
    is now async (Shape B patch.object migration — fallback_mock uses
    AsyncMock).
    """
    import numpy as np
    from unittest.mock import patch, AsyncMock
    import core.voice as _voice_mod
    from core.config import MIC_SAMPLE_RATE

    audio = np.zeros(3 * MIC_SAMPLE_RATE, dtype=np.float32)

    fallback_sentinel = [{"start_sample": 0, "end_sample": len(audio),
                          "speaker_id": "p1", "speaker_score": 0.9}]

    before = _voice_mod.get_diarize_stats()["fallback_count"]
    # P0.R6.Z D3.b: pyannote pipeline now lives subprocess-side. To simulate
    # a pyannote runtime failure, mock hw.run_heavy to RAISE — the outer
    # except in _diarize_pyannote catches and routes to ecapa_valley
    # fallback per existing DIARIZATION_FALLBACK_ON_ERROR logic.
    # P0.R6.Y D3: _diarize_ecapa_valley is async → inline AsyncMock so
    # A10 sees it within the 200-char context window.
    with patch("core.heavy_worker.run_heavy",
               new=AsyncMock(side_effect=RuntimeError("simulated pyannote runtime failure"))), \
         patch.object(_voice_mod, "_diarize_ecapa_valley",
                      AsyncMock(return_value=fallback_sentinel)) as fallback_mock:
        segs = await _voice_mod.diarize(audio, voice_gallery={"p1": np.ones(192)})
    after = _voice_mod.get_diarize_stats()["fallback_count"]

    fallback_mock.assert_called_once()
    assert after == before + 1, "fallback counter must bump on runtime error"
    # Shape normalization: even fallback output gets speaker_label=None
    # added by the dispatcher so callers see a uniform schema.
    assert len(segs) == 1
    assert segs[0]["speaker_label"] is None


def test_pipeline_uses_emotion_agents_dict():
    """pipeline.py must track emotion agents per person via PerPersonAgentStore."""
    import pipeline
    assert hasattr(pipeline, "_per_person_agent_store"), \
        "pipeline must have _per_person_agent_store for per-person agent tracking"
    assert isinstance(pipeline._per_person_agent_store.peek_all_emotion_agents(), dict), \
        "peek_all_emotion_agents() must return a dict (person_id → EmotionAgent)"


def test_whisper_vad_filter_disabled():
    """Pipeline's own VAD gates recording; Whisper's internal VAD must be off.

    P0.R6.X migration: the model.transcribe(vad_filter=False) call moved from
    core/audio.py into core/heavy_worker.py::whisper_transcribe_worker. Scan
    BOTH files so the invariant survives the migration regardless of where
    the inference call lives.
    """
    import ast, pathlib
    for path in ("core/audio.py", "core/heavy_worker.py"):
        src = pathlib.Path(path).read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg == "vad_filter":
                assert ast.literal_eval(node.value) is False, (
                    f"vad_filter must be False in {path}"
                )
                return
    pytest.fail("vad_filter keyword not found in core/audio.py or core/heavy_worker.py")


def test_whisper_uses_speaker_languages_config():
    src = Path(__file__).parent.parent.joinpath("core", "audio.py").read_text(encoding="utf-8")
    assert "SPEAKER_LANGUAGES[0]" in src, \
        "transcribe() must use SPEAKER_LANGUAGES[0], not a hard-coded language string"


def test_record_until_silence_publishes_speech_duration():
    """Session 78 Item 1: record_until_silence must publish speech-only
    duration via _last_speech_secs module-level state. Previous code
    measured buffer duration (pre-roll + speech + trailing silence, always
    > 1s), which made the VOICE_ROUTING_MIN_UTTERANCE_SECS floor a no-op.
    Source-inspection — the assignment must happen inside the function
    body, not as a no-op default."""
    src = Path(__file__).parent.parent.joinpath("core", "audio.py").read_text(encoding="utf-8")
    assert "_last_speech_secs" in src, (
        "record_until_silence must publish speech duration for the floor"
    )
    assert "speech_chunks * chunk_dur" in src, (
        "must be speech-only duration — NOT buffer duration "
        "(the latter was the Session 78 bug)"
    )


def test_last_speech_secs_only_published_on_non_empty_recording():
    """Session 79 Item 2: the publish must happen AFTER the empty-return
    check, NOT before. The original Session 78 version asserted the opposite
    — and that bug showed up live: the pipeline's post-turn addendum probe
    (3s empty listen looking for continuation speech) was clobbering the
    main turn's published duration with 0.0 before the routing gate could
    read it. Every [Voice] Routing log in the 2026-04-22 live session
    showed '0.00s < 1.0s floor' as a result. Fix: only publish when the
    recording actually produced usable audio; empty probes leave the
    previous value intact."""
    src = Path(__file__).parent.parent.joinpath("core", "audio.py").read_text(encoding="utf-8")
    idx_assign = src.find("_last_speech_secs = speech_chunks * chunk_dur")
    idx_early_return = src.find("return np.array([], dtype=np.float32)")
    assert idx_assign > -1, "publish line must exist"
    assert idx_early_return > -1, "empty-return sentinel must exist"
    assert idx_assign > idx_early_return, (
        "_last_speech_secs assignment must come AFTER the empty-recording "
        "early-return so zero-speech probes (e.g. post-turn addendum "
        "window) do not clobber the main turn's published duration"
    )


async def test_transcribe_prints_stt_with_timestamp_and_latency(capsys, monkeypatch):
    """Step 1 observability: transcribe()'s STT print must include HH:MM:SS.mmm
    and (Nms) latency tag so each line is latency-attributable.

    P0.R6.X migration: transcribe() is async and offloads to hw.run_heavy.
    Monkeypatches hw.run_heavy to return the expected text without spinning
    up a worker subprocess.
    """
    import re
    import numpy as np
    from core import audio as _audio
    from core import heavy_worker as _hw

    async def _stub_run_heavy(task_name, fn, *args, **kwargs):
        return ("hello there", kwargs.get("language", "en"))

    monkeypatch.setattr(_hw, "run_heavy", _stub_run_heavy)
    fake_audio = np.ones(16000, dtype=np.float32)
    capsys.readouterr()  # clear
    text, lang = await _audio.transcribe(fake_audio)
    out = capsys.readouterr().out
    assert text == "hello there"
    # STT line must have timestamp + latency tag
    assert re.search(r"\[STT\] \d{2}:\d{2}:\d{2}\.\d{3} \(\d+ms\) 'hello there'", out), \
        f"expected timestamped STT line, got: {out!r}"
    # Module global is populated for pipeline.py's attributed log line to use
    assert _audio._last_stt_elapsed_ms > 0


def test_s3b4_format_two_speakers_uses_legacy_layout():
    """Phase 3B.4 — N=2 backward compat: format preserves the legacy
    `[Name1]: text\\n[Name2]: text` layout (no 'simultaneously' header).
    Existing brain parsers and tests around the 2-speaker case keep
    working unchanged."""
    from pipeline import _format_multispeaker_transcript
    pairs = [("Jagan", "what's the weather"), ("Lexi", "I need help")]
    brain_text, preview, labels = _format_multispeaker_transcript(pairs)
    assert "simultaneously" not in brain_text, (
        "N=2 must NOT use the 3-voice header — backward compat invariant"
    )
    assert brain_text == (
        "[Jagan]: what's the weather\n[Lexi]: I need help"
    )
    assert labels == ["Jagan", "Lexi"]
    assert "Jagan" in preview and "Lexi" in preview


def test_s3b4_format_three_speakers_uses_simultaneous_header():
    """Phase 3B.4 — N≥3 switches to the `[3 voices simultaneously]\\n...`
    layout. Reviewer's ask: separate lines + header naming exact count so
    brain sees the multi-speaker signal prominently and can route
    correctly (arbitration rules from 3B.3 fire cleanly here)."""
    from pipeline import _format_multispeaker_transcript
    pairs = [("Jagan", "hi all"), ("Lexi", "good morning"), ("Priya", "hello")]
    brain_text, preview, labels = _format_multispeaker_transcript(pairs)
    assert brain_text.startswith("[3 voices simultaneously]\n"), (
        f"missing N-voice header; got: {brain_text!r}"
    )
    for nm in ("Jagan", "Lexi", "Priya"):
        assert nm in brain_text, f"speaker {nm!r} missing from brain text"
    assert labels == ["Jagan", "Lexi", "Priya"]


def test_s3b4_format_unknown_speaker_gets_numbered_label():
    """Phase 3B.4 — a span with name=None (no gallery match) renders as
    `unknown_1`; multiple unknowns number sequentially (`unknown_1`,
    `unknown_2`) so the brain can distinguish them within the turn
    even without gallery identity."""
    from pipeline import _format_multispeaker_transcript
    pairs = [
        ("Jagan", "hello"),
        (None,    "who is this"),
        (None,    "another voice"),
    ]
    brain_text, preview, labels = _format_multispeaker_transcript(pairs)
    assert labels == ["Jagan", "unknown_1", "unknown_2"], (
        f"unknown numbering broken; got {labels!r}"
    )
    assert "unknown_1" in brain_text
    assert "unknown_2" in brain_text
    # Numbering restarts per call (no cross-utterance state).
    _, _, labels2 = _format_multispeaker_transcript([
        (None, "first"), (None, "second"),
    ])
    assert labels2 == ["unknown_1", "unknown_2"]


def test_s3b4_format_single_speaker_returns_empty_tuple():
    """Phase 3B.4 — fewer than 2 surviving transcripts means the caller
    should route as a normal single-speaker turn; the helper returns
    `("", "", [])` so the caller's `len() >= 2` gate naturally skips
    the multi-speaker path. Regression guard on the early-return."""
    from pipeline import _format_multispeaker_transcript
    assert _format_multispeaker_transcript([("Jagan", "hi")]) == ("", "", [])
    assert _format_multispeaker_transcript([]) == ("", "", [])


def test_s3b4_format_mixed_known_and_unknowns():
    """Phase 3B.4 — 4-speaker mixed case: 2 known + 2 unknown. Unknown
    names stay distinct (unknown_1, unknown_2); known names preserved.
    Exercises the reviewer-spec'd edge of real-world conference calls
    where the system recognizes some but not all voices."""
    from pipeline import _format_multispeaker_transcript
    pairs = [
        ("Jagan",   "topic 1"),
        (None,      "chiming in"),
        ("Lexi",    "yes and"),
        (None,      "another angle"),
    ]
    brain_text, _, labels = _format_multispeaker_transcript(pairs)
    assert labels == ["Jagan", "unknown_1", "Lexi", "unknown_2"], (
        f"mixed numbering broken; got {labels!r}"
    )
    assert brain_text.startswith("[4 voices simultaneously]\n")


def test_s3b4_pipeline_uses_formatter_helper_not_inline_building():
    """Phase 3B.4 — source-inspection guard that pipeline.run delegates
    multi-speaker formatting to `_format_multispeaker_transcript` rather
    than building transcript strings inline. Legacy inline construction
    (`[{_name}]: {_t.strip()}` literal) must be gone; replaced by the
    helper call that applies unknown_N numbering + layout choice."""
    import inspect, pipeline
    src = inspect.getsource(pipeline.run)
    assert "_format_multispeaker_transcript(" in src, (
        "pipeline.run must delegate transcript formatting to the helper"
    )
    # Regression guard: the OLD inline `_lines.append(f"[{_name}]:` pattern
    # must NOT be present any more (replaced by _named_pairs + helper).
    assert "_lines.append(f\"[{_name}]:" not in src, (
        "legacy inline transcript construction must be gone — "
        "replaced by helper delegation"
    )


def test_s3b4_n_speaker_guardrail_log_emitted_for_three_plus():
    """Phase 3B.4 — source-inspection guard that the N≥3 guardrail log
    line is emitted before the normal routing log so canary analysis can
    see `primary: X, others: [Y, Z]` attribution when 3+ speakers were
    diarized. The log signature is the canary contract; drift in the
    format breaks post-hoc analysis."""
    import inspect, pipeline
    src = inspect.getsource(pipeline.run)
    assert "N-speaker turn" in src, (
        "N-speaker guardrail log signature missing"
    )
    assert "primary:" in src and "others:" in src, (
        "guardrail log must name primary AND others for canary analysis"
    )
    # Must be gated on len >= 3 specifically (not >= 2), per spec.
    assert "len(_named_pairs) >= 3" in src, (
        "guardrail must fire only for N≥3 (N=2 stays quiet — legacy behavior)"
    )


def test_s3b4_non_primary_speakers_not_auto_opened_regression():
    """Phase 3B.4 — regression guard on the session-fragmentation safety
    property: a 3-speaker utterance must NOT auto-open new stranger
    sessions for the non-primary speakers. pipeline.run opens sessions
    via `_open_session`; the ONLY call sites in the voice-routing path
    are the voice-match (one pid) and the engagement-gate stranger
    path. Multi-speaker transcripts don't touch either. This test
    confirms `_format_multispeaker_transcript` doesn't call
    `_open_session` and the helper has no side-effects on session
    state."""
    import inspect, pipeline
    fn_src = inspect.getsource(pipeline._format_multispeaker_transcript)
    assert "_open_session" not in fn_src, (
        "formatter must have zero session-opening side-effects"
    )
    assert "_active_sessions" not in fn_src, (
        "formatter must be pure over its inputs (no global session-state reads)"
    )


def test_s118_pipeline_dispatch_drops_multi_segment_mismatch():
    """Session 118 Fix A — pipeline.run dispatch handles the new action
    by `continue`-ing the loop (drop the turn). Source-inspection guard
    that the action is wired with the same drop pattern as
    short_utterance_voice_mismatch."""
    import inspect, pipeline
    src = inspect.getsource(pipeline.run)
    assert "multi_segment_voice_mismatch" in src, (
        "dispatch handler missing for new action"
    )


def test_pipeline_dispatch_handles_single_segment_voice_mismatch():
    """Session 120 — pipeline.run must dispatch the new action via
    `continue` (drop the turn), same shape as Session 118's
    multi_segment_voice_mismatch handler."""
    import inspect, pipeline
    src = inspect.getsource(pipeline.run)
    assert "single_segment_voice_mismatch" in src, (
        "dispatch handler missing for Session 120 action"
    )


def test_s118_pyannote_tf32_filter_targets_message_pattern():
    """Session 118 Fix B — pyannote ReproducibilityWarning suppression
    via message-pattern filter (catches before pyannote class is
    importable) AND class-import filter (defense-in-depth). Both must
    be present in pipeline.py for the warning to be silenced."""
    import inspect, pipeline
    src = inspect.getsource(pipeline)
    assert "TensorFloat-32" in src or "TF32" in src, (
        "TF32 message-pattern filter missing"
    )
    assert "ReproducibilityWarning" in src, (
        "class-import filter for ReproducibilityWarning missing"
    )


def test_s118_pyannote_tf32_filter_runs_before_imports():
    """Session 118 Fix B — the warning filter must be set BEFORE any
    pyannote-touching import so the suppression covers pyannote's init
    path. Source ordering check: filterwarnings calls precede the
    `from core.config import` block (which transitively triggers
    pyannote via voice.py loading)."""
    import inspect, pipeline
    src = inspect.getsource(pipeline)
    # Find positions: the message filter + the core.config import.
    tf32_pos = src.find("TensorFloat-32")
    config_import_pos = src.find("from core.config import (")
    assert tf32_pos >= 0 and config_import_pos >= 0
    assert tf32_pos < config_import_pos, (
        f"TF32 filter at pos {tf32_pos} must precede core.config import "
        f"at pos {config_import_pos}"
    )


async def test_transcribe_filters_char_level_repetition_hallucination(capsys, monkeypatch):
    """Session 105 Obs A: Whisper emits long runs of a single character
    ('Mmmmm' × 500) when it hallucinates on ambient noise. 2026-04-23
    canary line 444 had this artifact. Word-level filter doesn't catch
    it (single token). Char-run regex `(.)\\1{15,}` matches 16+ char
    runs — no natural utterance produces that pattern in STT output.

    P0.R6.X migration: transcribe() is async and offloads to hw.run_heavy.
    Monkeypatches hw.run_heavy to return the 500-char hallucination shape;
    the main-process filter chain (Q2 (b) lock) catches it.
    """
    import numpy as np
    from core import audio as _audio
    from core import heavy_worker as _hw

    # 500-char run of 'M' — the exact canary shape.
    mmmm = "M" * 500

    async def _stub_run_heavy(task_name, fn, *args, **kwargs):
        return (mmmm, kwargs.get("language", "en"))

    monkeypatch.setattr(_hw, "run_heavy", _stub_run_heavy)
    fake_audio = np.ones(16000, dtype=np.float32)
    capsys.readouterr()
    text, _ = await _audio.transcribe(fake_audio)
    out = capsys.readouterr().out
    assert text == "", (
        "char-run hallucination must be filtered to empty string — no "
        "turn should land in the pipeline"
    )
    assert "char-run hallucination filtered" in out, (
        "filter must log its decision so operators can see the reject "
        "rate"
    )


async def test_transcribe_allows_short_char_runs(capsys, monkeypatch):
    """Session 105 Obs A safety: real utterances with short char runs
    ('Ohhh', 'Mmm', 'Aaaa') must pass through. Threshold 15+ means
    6-char runs are fine.

    P0.R6.X migration: transcribe() is async and offloads to hw.run_heavy.
    """
    import numpy as np
    from core import audio as _audio
    from core import heavy_worker as _hw

    async def _stub_run_heavy(task_name, fn, *args, **kwargs):
        return ("Ohhhh that's interesting", kwargs.get("language", "en"))

    monkeypatch.setattr(_hw, "run_heavy", _stub_run_heavy)
    fake_audio = np.ones(16000, dtype=np.float32)
    text, _ = await _audio.transcribe(fake_audio)
    assert text == "Ohhhh that's interesting", (
        "4-char 'h' run must pass — threshold is 15+ consecutive chars"
    )
