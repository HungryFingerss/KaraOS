"""P0.R6.Z D3.c RETIREMENT (2026-05-24): this file previously tested the
Wave 3 Item 14 `_warmup_models` + `_warm_pyannote_via_dedicated_executor`
functions in ``pipeline.py``. Post-P0.R6.Z, the pyannote warm-up moved
to the ``run()`` startup 4-pool block via
``hw.get_or_create_pool("pyannote_diarize")``; the
``_warm_pyannote_via_dedicated_executor`` function is hard-deleted per
Q1 (a) lock.

The 4 test methods that targeted the retired pattern are deleted:
- ``test_warmup_calls_pyannote_loader`` —
  semantically replaced by P0.R6.Z A9 4-pool ordering invariant
  anchor (asserts ``hw.get_or_create_pool("pyannote_diarize")`` lands
  before vision task spawn).
- ``test_warmup_calls_ecapa_loader`` —
  retained via the ECAPA loader still being called from
  ``_warmup_models`` body for backward-compat (per P0.R6.Y closure
  note (7)).
- ``test_warmup_failure_isolated_does_not_block_others`` —
  retained semantically via the ``try/except`` inside
  ``_warmup_models._warm`` helper; pyannote no longer participates
  in the warmup task list.
- ``test_warmup_uses_dedicated_executor_for_pyannote`` —
  semantically replaced by P0.R6.Z A5 + A6 retirement inverse
  anchors (asserts ``_warm_pyannote_via_dedicated_executor`` +
  ``get_diarize_executor`` references are gone from production).

File retained (not deleted) to preserve grep-discoverability of the
retirement event + as a single-source-of-truth pointer for future
maintainers wondering where the warmup tests went.
"""
import pytest

import core.voice as voice_mod


def test_warm_pyannote_via_dedicated_executor_retired() -> None:
    """P0.R6.Z D3.c inverse: the ``_warm_pyannote_via_dedicated_executor``
    function on ``pipeline`` module MUST be absent. Canonical inverse-
    anchor coverage lives at
    ``tests/test_p0_r6_z_pyannote_worker.py::A6``.
    """
    import pipeline as _pl
    assert not hasattr(_pl, "_warm_pyannote_via_dedicated_executor"), (
        "P0.R6.Z D3.c RETIREMENT regression: "
        "`_warm_pyannote_via_dedicated_executor` still present on "
        "pipeline module surface — should have been hard-deleted per "
        "Q1 (a) lock."
    )
