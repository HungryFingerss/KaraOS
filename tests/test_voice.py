"""P0.R6.Z D3.a RETIREMENT (2026-05-24): this file previously tested the
Wave 3 Item 13 dedicated diarization ThreadPoolExecutor pattern
(``_voice_diarize_executor`` + ``get_diarize_executor()`` +
``shutdown_diarize_executor()``). All 3 symbols hard-deleted at P0.R6.Z
per Q1 (a) lock; pyannote inference now runs in the
``core/heavy_worker.py`` ProcessPoolExecutor subprocess via
``hw.run_heavy("pyannote_diarize", ...)``.

The 3 test methods that targeted the retired pattern are deleted:
- ``test_diarize_executor_singleton_returns_same_instance`` —
  semantically replaced by the subprocess-pool singleton at
  ``core/heavy_worker.py`` (covered by P0.R6.Z A2 anchor).
- ``test_diarize_executor_thread_name_prefix`` —
  semantically replaced by ``mp.get_context("spawn")`` subprocess
  isolation (covered by P0.R6 A2 anchor — already enforced).
- ``test_pipeline_uses_dedicated_executor_for_diarize`` —
  semantically replaced by P0.R6.Z A5 retirement inverse anchor
  (asserts ``get_diarize_executor`` reference is gone from
  ``core/voice.py``) + A6 retirement inverse anchor (asserts
  ``voice_mod.get_diarize_executor`` reference is gone from
  ``pipeline.py``).

File retained (not deleted) to preserve grep-discoverability of the
retirement event + as a single-source-of-truth pointer for future
maintainers wondering where the executor tests went.
"""
import pytest

import core.voice as voice_mod


def test_voice_diarize_executor_pattern_retired() -> None:
    """P0.R6.Z D3.a inverse: all 3 retired symbols MUST be absent from
    ``core.voice`` module surface. Sanity check that the retirement
    landed; canonical inverse-anchor coverage lives at
    ``tests/test_p0_r6_z_pyannote_worker.py::A5``.
    """
    for retired in (
        "_voice_diarize_executor",
        "get_diarize_executor",
        "shutdown_diarize_executor",
    ):
        assert not hasattr(voice_mod, retired), (
            f"P0.R6.Z D3.a RETIREMENT regression: `{retired}` still "
            f"present on core.voice module surface — should have been "
            f"hard-deleted per Q1 (a) lock."
        )
