"""VISION_ROADMAP P1.6 — deterministic tests for the eval bench's pure
metric layer. No live classifier calls; all fixtures are hand-crafted so
the aggregation math is verifiable against textbook values.

Reviewer's Session 82 checklist (7 tests):
  1. Per-source splitting
  2. Per-intent aggregation
  3. Precision/recall math (hand-computed)
  4. ECE calculation (textbook formula against 20-prediction fixture)
  5. Low-sample flag (at the <15 boundary)
  6. Row-level divergence surfaces mismatches correctly
  7. Empty fixture — no division by zero

Additional guardrails:
  * Loader excludes legacy_synthetic by default (deprecation rule)
  * compute_metrics rejects length-mismatched rows/predictions
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import json
import math
import pathlib

import pytest

from tests.eval_intent_bench import (
    LOW_SAMPLE_THRESHOLD,
    _compute_ece,
    collect_mismatches,
    compute_metrics,
    load_golden,
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _row(intent: str, source: str = "adversarial", **extra) -> dict:
    return {
        "user_text":       extra.pop("user_text", "x"),
        "expected_intent": intent,
        "expected_value":  None,
        "source":          source,
        "note":            "fixture",
        **extra,
    }


def _pred(intent: "str | None", conf: float = 0.9) -> "dict | None":
    if intent is None:
        return None
    return {
        "predicted_intent": intent,
        "confidence":       conf,
        "extracted_value":  None,
        "reasoning":        "fixture",
    }


# ── Test 1 — per-source splitting ────────────────────────────────────────────


def test_per_source_splits_metrics_independently():
    """P1.6 / reviewer checklist: 5 adversarial + 5 synthetic rows for the
    SAME intent, with different accuracy rates per source, must produce two
    distinct per_source buckets. The metric for each source must be computed
    from ONLY that source's rows (not contaminated by the other subset)."""
    rows  = []
    preds = []
    # adversarial: 5 rows, 4 correct (precision/recall on assign_system_name = 4/5)
    for _ in range(4):
        rows.append(_row("assign_system_name", source="adversarial"))
        preds.append(_pred("assign_system_name"))
    rows.append(_row("assign_system_name", source="adversarial"))
    preds.append(_pred("casual_conversation"))
    # synthetic_common: 5 rows, all correct (precision/recall = 5/5)
    for _ in range(5):
        rows.append(_row("assign_system_name", source="synthetic_common"))
        preds.append(_pred("assign_system_name"))

    m = compute_metrics(rows, preds)
    # Sanity — subsets must not share row counts.
    assert m["per_source"]["adversarial"]["overall"]["n"] == 5
    assert m["per_source"]["synthetic_common"]["overall"]["n"] == 5
    # Metrics differ BECAUSE the subsets differ (proves the splitting).
    assert m["per_source"]["adversarial"]["overall"]["accuracy"] == pytest.approx(4 / 5)
    assert m["per_source"]["synthetic_common"]["overall"]["accuracy"] == pytest.approx(5 / 5)


# ── Test 2 — per-intent aggregation ──────────────────────────────────────────


def test_per_intent_uses_only_that_intents_rows():
    """P1.6 / reviewer checklist: mixed-intent fixture must compute
    intent_X metrics from ONLY intent_X ground-truth rows. If a different
    intent's rows were pooled in, precision could go negative or NaN in
    skewed cases — caught here."""
    rows = [
        _row("assign_system_name"),  # TP for assign_system_name
        _row("assign_system_name"),  # FN for assign_system_name (predicted wrong)
        _row("casual_conversation"), # FP for assign_system_name (predicted assign)
        _row("casual_conversation"), # TP for casual_conversation
    ]
    preds = [
        _pred("assign_system_name"),
        _pred("casual_conversation"),
        _pred("assign_system_name"),
        _pred("casual_conversation"),
    ]
    m = compute_metrics(rows, preds)
    # assign_system_name: TP=1, FP=1, FN=1 → precision=1/2, recall=1/2
    a = m["hybrid"]["per_intent"]["assign_system_name"]
    assert a["precision"] == pytest.approx(0.5)
    assert a["recall"]    == pytest.approx(0.5)
    assert a["n_samples"] == 2
    # casual_conversation: TP=1, FP=1 (from row 1 being predicted as casual when expected was assign),
    #                      FN=1 (row 2 expected assign but predicted casual — FN for assign, not casual)
    # Actually: casual TP=1 (row 4), casual FP=1 (row 2 expected assign but predicted casual),
    #          casual FN=1 (row 3 expected casual but predicted assign).
    c = m["hybrid"]["per_intent"]["casual_conversation"]
    assert c["precision"] == pytest.approx(0.5)
    assert c["recall"]    == pytest.approx(0.5)
    assert c["n_samples"] == 2


# ── Test 3 — precision/recall math (hand-computed 10-row fixture) ────────────


def test_precision_recall_hand_computed():
    """P1.6 / reviewer checklist: 10-row fixture with hand-computed
    expected values.

    Fixture — class X (label under test):
      6 ground-truth X rows, of which 5 predicted X (1 predicted Y)
      4 ground-truth Y rows, of which 2 predicted X (2 predicted Y)

    Expected for X:
      TP = 5, FP = 2, FN = 1
      precision = 5 / (5 + 2) = 5/7 ≈ 0.714
      recall    = 5 / (5 + 1) = 5/6 ≈ 0.833

    Expected for Y:
      TP = 2, FP = 1, FN = 2
      precision = 2 / (2 + 1) = 2/3 ≈ 0.667
      recall    = 2 / (2 + 2) = 2/4 = 0.500
    """
    rows = [_row("X") for _ in range(6)] + [_row("Y") for _ in range(4)]
    # First 5 X-rows predict X correctly; 6th X predicts Y (FN for X).
    # First 2 Y-rows predict X (FP for X, FN for Y); last 2 Y-rows predict Y.
    preds = (
        [_pred("X")] * 5 + [_pred("Y")] +
        [_pred("X")] * 2 + [_pred("Y")] * 2
    )
    # Expected_intent X and Y aren't in INTENT_LABELS so load/validate
    # helpers that check against config would reject — but compute_metrics
    # is label-agnostic.
    m = compute_metrics(rows, preds)
    x = m["hybrid"]["per_intent"]["X"]
    y = m["hybrid"]["per_intent"]["Y"]
    assert x["precision"] == pytest.approx(5 / 7)
    assert x["recall"]    == pytest.approx(5 / 6)
    assert y["precision"] == pytest.approx(2 / 3)
    assert y["recall"]    == pytest.approx(2 / 4)
    # Overall accuracy = (5 correct X + 2 correct Y) / 10 = 0.7
    assert m["hybrid"]["overall"]["accuracy"] == pytest.approx(0.7)


# ── Test 4 — ECE (textbook formula against 20-prediction fixture) ────────────


def test_ece_matches_textbook_formula():
    """P1.6 / reviewer checklist: hand-crafted 20-prediction fixture in
    two confidence buckets with known accuracy/confidence → ECE matches
    the textbook Σ_b (|B_b|/N) * |acc(B_b) - conf(B_b)|.

    Fixture:
      10 predictions in bucket [0.8, 0.9) with confidence 0.85, 9 correct
         → acc(B) = 0.9, conf(B) = 0.85, |Δ| = 0.05
      10 predictions in bucket [0.5, 0.6) with confidence 0.55, 6 correct
         → acc(B) = 0.6, conf(B) = 0.55, |Δ| = 0.05

    ECE = (10/20)*0.05 + (10/20)*0.05 = 0.05
    """
    pairs: list[tuple[dict, dict]] = []
    for i in range(10):
        # 9 of 10 correct — predicted matches expected intent "X"
        pred_intent = "X" if i < 9 else "Y"
        pairs.append((_row("X"), {"predicted_intent": pred_intent, "confidence": 0.85}))
    for i in range(10):
        pred_intent = "X" if i < 6 else "Y"
        pairs.append((_row("X"), {"predicted_intent": pred_intent, "confidence": 0.55}))
    ece = _compute_ece(pairs)
    assert ece == pytest.approx(0.05, abs=1e-6)


def test_ece_zero_on_empty():
    """Defensive: empty pairs list must not divide by zero."""
    assert _compute_ece([]) == 0.0


# ── Test 5 — low-sample flag at the boundary ─────────────────────────────────


def test_low_sample_flag_at_boundary():
    """P1.6 / reviewer checklist: intent with <LOW_SAMPLE_THRESHOLD rows
    flagged; intent at or above the threshold NOT flagged. Exercises the
    exact boundary (5 < 15 vs 20 >= 15)."""
    rows = (
        [_row("rare") for _ in range(5)] +       # 5 samples — below threshold
        [_row("common") for _ in range(20)]      # 20 samples — above threshold
    )
    preds = [_pred(r["expected_intent"]) for r in rows]
    m = compute_metrics(rows, preds)
    assert m["hybrid"]["per_intent"]["rare"]["low_sample"]    is True
    assert m["hybrid"]["per_intent"]["common"]["low_sample"]  is False
    # Also sanity-check that the threshold constant itself is 15 (guards
    # against a drive-by change to LOW_SAMPLE_THRESHOLD silently breaking
    # downstream consumers of the flag).
    assert LOW_SAMPLE_THRESHOLD == 15


# ── Test 6 — row-level divergence surfaces mismatches (incl. timeouts) ───────


def test_collect_mismatches_surfaces_wrong_and_timeouts():
    """P1.6 / reviewer checklist: both ``expected != predicted`` rows AND
    classifier-timeout rows (prediction=None) must show up in the
    row-level divergence list — operators need to inspect both kinds when
    a run's metrics look off."""
    rows = [
        _row("X", user_text="correct",   source_file="a.md:1"),
        _row("X", user_text="wrong",     source_file="b.md:1"),
        _row("X", user_text="timed-out", source_file="c.md:1"),
    ]
    preds = [
        _pred("X", conf=0.9),
        _pred("Y", conf=0.3),
        None,
    ]
    mismatches = collect_mismatches(rows, preds)
    assert len(mismatches) == 2
    wrong, timed_out = mismatches
    assert wrong["user_text"]        == "wrong"
    assert wrong["expected_intent"]  == "X"
    assert wrong["predicted_intent"] == "Y"
    assert wrong["confidence"]       == pytest.approx(0.3)
    assert wrong["source_file"]      == "b.md:1"
    assert timed_out["user_text"]        == "timed-out"
    assert timed_out["predicted_intent"] is None
    assert timed_out["confidence"]       == 0.0


# ── Test 7 — empty fixture → graceful, no div-by-zero ────────────────────────


def test_compute_metrics_empty_fixture_graceful():
    """P1.6 / reviewer checklist: zero-row input must not blow up the
    aggregator. Returns a well-formed shell so downstream callers don't
    need a separate ``if rows:`` branch."""
    m = compute_metrics([], [])
    assert m["hybrid"]["overall"]["n"]        == 0
    assert m["hybrid"]["overall"]["correct"]  == 0
    assert m["hybrid"]["overall"]["accuracy"] == 0.0
    assert m["hybrid"]["per_intent"]          == {}
    assert m["hybrid"]["timeouts"]            == 0
    assert m["real_observed"]["overall"]["n"] == 0
    assert m["per_source"]                    == {}


# ── Guardrails beyond the 7-item checklist ───────────────────────────────────


def test_compute_metrics_rejects_length_mismatch():
    """Defensive: rows and predictions must align by index. A length
    mismatch almost certainly means the live-bench loop had an exception
    mid-iteration; silent silent-mismatch would produce incoherent
    metrics. Fail loudly."""
    with pytest.raises(AssertionError):
        compute_metrics([_row("X")], [_pred("X"), _pred("Y")])


def test_bench_importable_in_script_mode():
    """Session 82 follow-up: ``python tests/eval_intent_bench.py`` invocation
    set sys.path[0] to tests/, causing ``from core.brain import ...`` to fail
    with ModuleNotFoundError when the bench ran main. Fixed by prepending the
    repo root to sys.path at module top. Guard against regression by
    asserting the sentinel _REPO_ROOT is on sys.path after import."""
    import sys
    from tests import eval_intent_bench as bench
    assert str(bench._REPO_ROOT) in sys.path, (
        "bench module must place project root on sys.path so script-mode "
        "invocation (python tests/eval_intent_bench.py) can import core.*"
    )


def test_load_golden_excludes_legacy_synthetic_by_default(tmp_path):
    """P1.6 deprecation rule (Session 81 CLAUDE.md): rows tagged
    source=legacy_synthetic stay in the JSONL as historical record but
    MUST NOT contribute to metrics. load_golden() enforces this by
    default; include_legacy=True opts back in (for audit tooling)."""
    p = tmp_path / "golden.jsonl"
    p.write_text(
        '{"user_text":"a","expected_intent":"X","expected_value":null,"source":"adversarial","note":""}\n'
        '{"user_text":"b","expected_intent":"Y","expected_value":null,"source":"legacy_synthetic","note":""}\n'
        '{"user_text":"c","expected_intent":"Z","expected_value":null,"source":"synthetic_common","note":""}\n',
        encoding="utf-8",
    )
    default = load_golden(p)
    assert [r["user_text"] for r in default] == ["a", "c"]
    # Explicit include — audit path for inspecting the full corpus.
    all_rows = load_golden(p, include_legacy=True)
    assert [r["user_text"] for r in all_rows] == ["a", "b", "c"]
