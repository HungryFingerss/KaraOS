"""SB.7 Steps 4-6 — baseline (A6) + --alert regression gate (A5) + Step-4 deferral.

Covers the Plan v1 §2 anchors that land with this bundle:

  * A5 — ``evaluate_alert`` trips past either D3 band and stays green within
    them, in BOTH directions (parametrized synthetic deltas); the boundary is
    inclusive (``>=``, mirroring eval_weekly); ``main(["--alert"])`` exits
    non-zero on a regression and zero on a clean run; a missing baseline is
    baseline-ESTABLISHING (exit 0) while a MALFORMED baseline fails CLOSED.
  * A6 — ``write_baseline`` round-trips byte-identically through
    ``load_baseline``; the COMMITTED ``baseline/baseline.json`` carries the
    D6 provenance (git SHA + seed + denominator + model pins) and sits within
    the D3 bands of a fresh real-driver run (acceptance #2 in CI form —
    band-comparison, not strict float equality, so cross-box BLAS last-bit
    noise can't flake the anchor).
  * Step 4 — ``--real-eer`` is DEFERRED per Plan v1 §5: exits 2 with the
    deferral note BEFORE any computation.

Discipline: tests write only under ``tmp_path`` (``_RUNS_DIR`` /
``_BASELINE_PATH`` monkeypatched); the committed baseline is READ-only here.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import json
import pathlib

import pytest

from bench.perception import bench
from core.config import PERCEPTION_ATTRIBUTION_DROP_PP, PERCEPTION_EER_REGRESSION_BAND

_COMMITTED_BASELINE = pathlib.Path(bench.__file__).resolve().parent / "baseline" / "baseline.json"

_BASE_EER = 0.0625      # the Step-5 freeze value — fixture-local, not a gate
_BASE_ACC = 1.0


def _metrics(eer: float, acc: float) -> dict:
    """A metrics dict shaped exactly like compute_metrics output."""
    return {
        "face_eer": {
            "eer": eer, "implied_threshold": 0.51,
            "n_genuine": 80, "n_impostor": 80, "seed": 20260702,
        },
        "attribution": {
            "accuracy": acc, "per_band": {"normal": acc},
            "mismatches": [], "denominator": 51,
        },
    }


def _baseline(eer: float = _BASE_EER, acc: float = _BASE_ACC) -> dict:
    """A baseline payload shaped exactly like write_baseline / save_run output."""
    return {
        "metrics": _metrics(eer, acc),
        "metadata": {
            "run_ts": "2026-07-02T00:00:00Z", "git_sha": "fixture",
            "seed": 20260702, "denominator": 51,
        },
    }


# --------------------------------------------------------------------------- #
# A5 — evaluate_alert: both bands, both directions, parametrized deltas.
# Deltas are expressed RELATIVE to the config bands (rule-gated, never a
# pre-blessed integer): retuning a band moves the cases with it.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("eer_delta", "acc_drop_pp", "expect_trip"),
    [
        pytest.param(0.0, 0.0, False, id="identical_run_clean"),
        pytest.param(PERCEPTION_EER_REGRESSION_BAND * 0.5, 0.0, False,
                     id="eer_rise_half_band_clean"),
        pytest.param(PERCEPTION_EER_REGRESSION_BAND - 1e-4, 0.0, False,
                     id="eer_rise_just_under_band_clean"),
        pytest.param(PERCEPTION_EER_REGRESSION_BAND + 1e-9, 0.0, True,
                     id="eer_rise_at_band_trips"),
        pytest.param(PERCEPTION_EER_REGRESSION_BAND * 2.0, 0.0, True,
                     id="eer_rise_past_band_trips"),
        pytest.param(-PERCEPTION_EER_REGRESSION_BAND * 2.0, 0.0, False,
                     id="eer_improvement_never_trips"),
        pytest.param(0.0, PERCEPTION_ATTRIBUTION_DROP_PP * 0.5, False,
                     id="attr_drop_half_band_clean"),
        pytest.param(0.0, PERCEPTION_ATTRIBUTION_DROP_PP - 0.01, False,
                     id="attr_drop_just_under_band_clean"),
        pytest.param(0.0, PERCEPTION_ATTRIBUTION_DROP_PP + 1e-6, True,
                     id="attr_drop_at_band_trips"),
        pytest.param(0.0, PERCEPTION_ATTRIBUTION_DROP_PP * 2.0, True,
                     id="attr_drop_past_band_trips"),
        pytest.param(PERCEPTION_EER_REGRESSION_BAND * 2.0,
                     PERCEPTION_ATTRIBUTION_DROP_PP * 2.0, True,
                     id="both_regress_trips"),
    ],
)
def test_a5_gate_parametrized_synthetic_deltas(eer_delta, acc_drop_pp, expect_trip) -> None:
    current = _metrics(_BASE_EER + eer_delta, _BASE_ACC - acc_drop_pp / 100.0)
    verdict = bench.evaluate_alert(current, _baseline())
    assert verdict["tripped"] is expect_trip, verdict["reasons"]
    if expect_trip:
        assert verdict["reasons"], "a tripped gate must name its reason(s)"


def test_a5_gate_boundary_is_inclusive() -> None:
    # The Plan v1 step-6 predicate is `>=` (mirrors eval_weekly): a delta
    # EXACTLY equal to the band trips. Bands are passed explicitly as the
    # exact computed deltas so float representation can't blur the boundary —
    # this anchor fails if `>=` ever regresses to `>`.
    current = _metrics(0.10, 0.90)
    exact_rise = current["face_eer"]["eer"] - _BASE_EER
    exact_drop_pp = (_BASE_ACC - current["attribution"]["accuracy"]) * 100.0

    eer_only = bench.evaluate_alert(
        current, _baseline(), eer_band=exact_rise, attribution_drop_pp=999.0)
    assert eer_only["tripped"] and any("EER regression" in r for r in eer_only["reasons"])

    attr_only = bench.evaluate_alert(
        current, _baseline(), eer_band=999.0, attribution_drop_pp=exact_drop_pp)
    assert attr_only["tripped"] and any(
        "attribution regression" in r for r in attr_only["reasons"])


def test_a5_attribution_band_honors_d3_floor_and_one_case_granularity() -> None:
    # D3 locks the attribution band at a >=2pp floor. With the current golden
    # denominator, ONE case flip must stay WITHIN the band (the per-case golden
    # tests hard-fail CI on any flip — the bench gate is the coarse drift
    # alarm); the gate trips only from two-flip-scale drops. Rule-gated against
    # the live golden count: shrinking the golden set below the granularity
    # assumption fails HERE, forcing a band re-tune.
    from tests.reconciler_golden import RECONCILER_GOLDEN_CASES

    assert PERCEPTION_ATTRIBUTION_DROP_PP >= 2.0
    single_flip_pp = 100.0 / len(RECONCILER_GOLDEN_CASES)
    assert single_flip_pp < PERCEPTION_ATTRIBUTION_DROP_PP, (
        "one golden-case flip now exceeds the attribution band — the D3 "
        "one-case-granularity floor no longer holds; re-derive the band"
    )
    one_flip = _metrics(_BASE_EER, _BASE_ACC - single_flip_pp / 100.0)
    assert bench.evaluate_alert(one_flip, _baseline())["tripped"] is False


def test_a5_missing_baseline_is_establishing_not_tripped() -> None:
    verdict = bench.evaluate_alert(_metrics(0.9, 0.1), None)
    assert verdict["tripped"] is False
    assert any("baseline-establishing" in r for r in verdict["reasons"])


def test_a5_malformed_baseline_fails_closed() -> None:
    # A PRESENT-but-truncated baseline is corruption, not absence: the gate
    # must trip (fail CLOSED) rather than silently pass every run.
    truncated = {"metrics": {"attribution": {"accuracy": 1.0}}, "metadata": {}}
    verdict = bench.evaluate_alert(_metrics(_BASE_EER, _BASE_ACC), truncated)
    assert verdict["tripped"] is True
    assert any("failing CLOSED" in r for r in verdict["reasons"])


# --------------------------------------------------------------------------- #
# A5 wiring — main(["--alert"]) exit codes. Metric drivers are monkeypatched
# to canned dicts (the drivers' own behavior is anchored in
# test_sb7_bench_skeleton.py); _RUNS_DIR + _BASELINE_PATH point at tmp_path so
# the repo tree is never written by a test.
# --------------------------------------------------------------------------- #
def _wire(monkeypatch, tmp_path, *, cur_eer: float, cur_acc: float,
          baseline: "dict | None") -> None:
    monkeypatch.setattr(bench, "_RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(bench, "_BASELINE_PATH", tmp_path / "baseline.json")
    metrics = _metrics(cur_eer, cur_acc)
    monkeypatch.setattr(bench, "compute_face_eer", lambda: dict(metrics["face_eer"]))
    monkeypatch.setattr(
        bench, "compute_attribution_accuracy", lambda: dict(metrics["attribution"]))
    if baseline is not None:
        bench.write_baseline(baseline["metrics"], baseline["metadata"])


def test_a5_main_alert_exits_1_on_regression(tmp_path, monkeypatch, capsys) -> None:
    _wire(monkeypatch, tmp_path,
          cur_eer=_BASE_EER + PERCEPTION_EER_REGRESSION_BAND * 2.0,
          cur_acc=_BASE_ACC, baseline=_baseline())
    rc = bench.main(["--alert"])
    assert rc == 1
    out = capsys.readouterr().out
    assert "TRIPPED" in out and "EER regression" in out


def test_a5_main_alert_exits_0_when_clean(tmp_path, monkeypatch, capsys) -> None:
    _wire(monkeypatch, tmp_path, cur_eer=_BASE_EER, cur_acc=_BASE_ACC,
          baseline=_baseline())
    rc = bench.main(["--alert"])
    assert rc == 0
    assert "alert gate clean" in capsys.readouterr().out


def test_a5_main_alert_without_baseline_is_establishing_exit_0(
        tmp_path, monkeypatch, capsys) -> None:
    _wire(monkeypatch, tmp_path, cur_eer=_BASE_EER, cur_acc=_BASE_ACC, baseline=None)
    rc = bench.main(["--alert"])
    assert rc == 0
    assert "baseline-establishing" in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# A6 — baseline persistence: round-trip + committed-artifact provenance.
# --------------------------------------------------------------------------- #
def test_a6_write_baseline_round_trips_via_load_baseline(tmp_path) -> None:
    payload = _baseline()
    path = bench.write_baseline(
        payload["metrics"], payload["metadata"], path=tmp_path / "b" / "baseline.json")
    assert path.exists()
    loaded = bench.load_baseline(path)
    assert loaded == payload          # save → load → identical (A6)


def test_a6_default_run_never_writes_baseline(tmp_path, monkeypatch) -> None:
    # D6: re-baselining is an explicit human-reviewed act. A flag-less run
    # must NEVER touch the baseline file.
    _wire(monkeypatch, tmp_path, cur_eer=_BASE_EER, cur_acc=_BASE_ACC, baseline=None)
    assert bench.main() == 0
    assert not (tmp_path / "baseline.json").exists()


def test_a6_committed_baseline_carries_d6_provenance() -> None:
    # The committed artifact (Step 5) — READ-only here. Provenance is
    # rule-gated against the live sources (committed .npz seed + golden
    # denominator), never pre-blessed integers.
    assert _COMMITTED_BASELINE.exists(), (
        "bench/perception/baseline/baseline.json missing — Step 5 establishes "
        "it via `python -m bench.perception --write-baseline` + human-reviewed commit"
    )
    payload = json.loads(_COMMITTED_BASELINE.read_text(encoding="utf-8"))
    assert set(payload) == {"metrics", "metadata"}

    md = payload["metadata"]
    assert isinstance(md["git_sha"], str) and md["git_sha"]

    import numpy as np
    npz = np.load(pathlib.Path(bench.__file__).resolve().parent
                  / "data" / "synthetic_embeddings.npz")
    assert md["seed"] == int(npz["seed"])

    from tests.reconciler_golden import EXPECTED_CASE_COUNT, RECONCILER_GOLDEN_CASES
    assert md["denominator"] == len(RECONCILER_GOLDEN_CASES) == EXPECTED_CASE_COUNT

    # Model/config pins (D6: a re-baseline review must see config drift).
    from core.config import EMBED_MODEL, RECOGNITION_THRESHOLD
    assert md["recognition_threshold"] == RECOGNITION_THRESHOLD
    assert md["embed_model"] == EMBED_MODEL

    metrics = payload["metrics"]
    assert 0.0 < metrics["face_eer"]["eer"] < 0.5          # non-degenerate
    assert 0.0 <= metrics["attribution"]["accuracy"] <= 1.0


def test_a6_committed_baseline_within_bands_of_fresh_run() -> None:
    # Acceptance #2 in CI form: a REAL fresh run (both drivers, real FaceDB +
    # real reconcile) diffed against the committed baseline through the D3
    # gate must be clean. Band-comparison rather than strict equality so
    # cross-box BLAS last-bit noise can't flake the anchor; on the freeze box
    # the run is byte-identical anyway (A4).
    baseline = bench.load_baseline()
    assert baseline is not None, "committed baseline missing (Step 5)"
    fresh = bench.compute_metrics(
        eer=bench.compute_face_eer(),
        attribution=bench.compute_attribution_accuracy(),
    )
    verdict = bench.evaluate_alert(fresh, baseline)
    assert verdict["tripped"] is False, verdict["reasons"]


# --------------------------------------------------------------------------- #
# Step 4 — --real-eer DEFERRED per Plan v1 §5: exit 2, deferral note, and
# NOTHING computed or persisted (a deferral must never look like a run).
# --------------------------------------------------------------------------- #
def test_step4_real_eer_defers_with_exit_2_and_no_run(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(bench, "_RUNS_DIR", tmp_path)

    def _boom() -> dict:
        raise AssertionError("--real-eer must exit BEFORE any metric driver runs")

    monkeypatch.setattr(bench, "compute_face_eer", _boom)
    monkeypatch.setattr(bench, "compute_attribution_accuracy", _boom)

    rc = bench.main(["--real-eer"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "DEFERRED" in err and "Plan v1 §5" in err
    assert list(tmp_path.glob("*.json")) == []


# --------------------------------------------------------------------------- #
# Surface — the Steps 4-6 additions are present + importable.
# --------------------------------------------------------------------------- #
def test_bench_exposes_gate_and_baseline_surface() -> None:
    for name in ("evaluate_alert", "write_baseline", "load_baseline", "main"):
        assert callable(getattr(bench, name)), f"bench.{name} missing/not callable"
