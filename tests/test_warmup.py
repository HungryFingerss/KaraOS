"""
Tests for pipeline._warmup_models — Wave 3 Item 14: model warmup at boot.

These tests require the production venv (torchaudio, onnxruntime).
They run automatically with pytest in the full environment.
"""
import asyncio
import inspect
import pytest
import core.voice as voice_mod


@pytest.mark.slow
@pytest.mark.models
class TestWarmupModels:
    """Marked slow+models: triggers `core.voice` import + monkeypatches real
    pyannote/SpeechBrain loaders. Fast CI skips; nightly CI runs."""

    def setup_method(self):
        # Ensure executor is clean so tests don't share state
        voice_mod._voice_diarize_executor = None

    def teardown_method(self):
        voice_mod.shutdown_diarize_executor()

    async def test_warmup_calls_pyannote_loader(self, monkeypatch):
        """_warmup_models calls _load_pyannote_pipeline exactly once."""
        import pipeline

        call_count = {"n": 0}

        def _fake_pyannote():
            call_count["n"] += 1

        monkeypatch.setattr(voice_mod, "_load_pyannote_pipeline", _fake_pyannote)
        monkeypatch.setattr(voice_mod, "load_speaker_embedder", lambda: None)

        loop = asyncio.get_running_loop()
        await pipeline._warmup_models(loop)

        assert call_count["n"] == 1, (
            f"_load_pyannote_pipeline should be called once; got {call_count['n']}"
        )

    async def test_warmup_calls_ecapa_loader(self, monkeypatch):
        """_warmup_models calls load_speaker_embedder exactly once."""
        import pipeline

        call_count = {"n": 0}

        def _fake_ecapa():
            call_count["n"] += 1

        monkeypatch.setattr(voice_mod, "_load_pyannote_pipeline", lambda: None)
        monkeypatch.setattr(voice_mod, "load_speaker_embedder", _fake_ecapa)

        loop = asyncio.get_running_loop()
        await pipeline._warmup_models(loop)

        assert call_count["n"] == 1, (
            f"load_speaker_embedder should be called once; got {call_count['n']}"
        )

    async def test_warmup_failure_isolated_does_not_block_others(self, monkeypatch):
        """A failing loader does not prevent other loaders from completing."""
        import pipeline

        completed = {"ecapa": False}

        def _boom():
            raise RuntimeError("simulated pyannote load failure")

        def _ok_ecapa():
            completed["ecapa"] = True

        monkeypatch.setattr(voice_mod, "_load_pyannote_pipeline", _boom)
        monkeypatch.setattr(voice_mod, "load_speaker_embedder", _ok_ecapa)

        # Must not raise — failures are caught internally
        loop = asyncio.get_running_loop()
        await pipeline._warmup_models(loop)

        assert completed["ecapa"], (
            "ECAPA loader must complete even when pyannote loader raises"
        )

    def test_warmup_uses_dedicated_executor_for_pyannote(self):
        """_warm_pyannote_via_dedicated_executor calls voice_mod.get_diarize_executor()."""
        import pipeline
        src = inspect.getsource(pipeline._warm_pyannote_via_dedicated_executor)
        assert "get_diarize_executor()" in src, (
            "_warm_pyannote_via_dedicated_executor must call voice_mod.get_diarize_executor()"
        )
