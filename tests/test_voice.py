"""
Tests for core/voice.py — Wave 3 Item 13: dedicated diarization executor.
"""
import inspect
import threading
import pytest
import core.voice as voice_mod


def _reset_executor():
    """Reset module-level executor singleton between tests."""
    voice_mod._voice_diarize_executor = None


@pytest.mark.slow
@pytest.mark.models
class TestDiarizeExecutor:
    """Marked slow+models: imports `core.voice` which drags real torchaudio
    + speechbrain + pyannote into scope. Fast CI skips; nightly CI runs."""

    def setup_method(self):
        _reset_executor()

    def teardown_method(self):
        # clean up after each test so threads don't linger
        voice_mod.shutdown_diarize_executor()

    def test_diarize_executor_singleton_returns_same_instance(self):
        """get_diarize_executor() twice returns the identical object."""
        ex1 = voice_mod.get_diarize_executor()
        ex2 = voice_mod.get_diarize_executor()
        assert ex1 is ex2

    def test_diarize_executor_thread_name_prefix(self):
        """Worker thread name starts with 'voice-diarize'."""
        ex = voice_mod.get_diarize_executor()
        names: list[str] = []
        fut = ex.submit(lambda: names.append(threading.current_thread().name))
        fut.result(timeout=5)
        assert names and names[0].startswith("voice-diarize"), (
            f"Thread name {names[0]!r} doesn't start with 'voice-diarize'"
        )

    def test_pipeline_uses_dedicated_executor_for_diarize(self):
        """Every voice_mod.diarize call in pipeline.py uses get_diarize_executor(), not None."""
        import pathlib
        src = pathlib.Path("pipeline.py").read_text(encoding="utf-8")
        # Confirm the dedicated executor is used
        assert "voice_mod.get_diarize_executor()" in src, (
            "pipeline.py should pass voice_mod.get_diarize_executor() to run_in_executor"
        )
        # Confirm None is NOT used alongside voice_mod.diarize
        lines = src.splitlines()
        for i, line in enumerate(lines):
            if "voice_mod.diarize" in line or "voice_mod.get_diarize_executor" in line:
                # look at the surrounding context (the run_in_executor call)
                window = "\n".join(lines[max(0, i - 3):i + 3])
                if "voice_mod.diarize" in window:
                    assert "get_diarize_executor()" in window, (
                        f"voice_mod.diarize call near line {i+1} does not use "
                        f"get_diarize_executor():\n{window}"
                    )
                    assert "run_in_executor(None," not in window.replace(
                        "get_diarize_executor()", ""
                    ), (
                        f"voice_mod.diarize call near line {i+1} still uses None executor"
                    )
