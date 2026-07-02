"""SB.7 Step 1 — bench skeleton suite-green proof.

Exercises the PURE metrics layer of ``bench/perception/bench.py`` with synthetic
metric dicts, the persistence + metadata surface, AND the two built metric
drivers: Step 2c (attribution over the golden cases via the real ``reconcile``)
+ Step 3 (face-EER over the committed synthetic set via a real ``FaceDB`` —
PI-2 locked by the A3 detector below). The Steps 4-6 anchors (A5 --alert gate,
A6 baseline, --real-eer deferral) live in ``tests/test_sb7_bench_gate.py``.

Discipline: ``save_run`` writes only under ``tmp_path``; ``load_baseline`` reads
only the path it is handed — NEVER the committed ``baseline/baseline.json`` or
any production tree.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import ast
import json
import math
import pathlib

import pytest

from bench.perception import bench


# --------------------------------------------------------------------------- #
# Fixtures — synthetic metric dicts shaped like the Step-2/Step-3 driver output.
# --------------------------------------------------------------------------- #
def _eer_result() -> dict:
    return {
        "eer": 0.0421,
        "implied_threshold": 0.31,
        "n_genuine": 90,
        "n_impostor": 810,
        "seed": 1234,
    }


def _attribution_result() -> dict:
    return {
        "accuracy": 0.9655,
        "per_band": {"short_hard": 1.0, "normal": 0.95},
        "mismatches": [{"id": "n4b_x", "expected": "current", "got": "new_stranger"}],
        "denominator": 58,
    }


# --------------------------------------------------------------------------- #
# compute_metrics — pure aggregation: structure, determinism, no mutation.
# --------------------------------------------------------------------------- #
def test_compute_metrics_structures_both_metrics() -> None:
    metrics = bench.compute_metrics(eer=_eer_result(), attribution=_attribution_result())
    assert set(metrics) == {"face_eer", "attribution"}
    assert metrics["face_eer"]["eer"] == 0.0421
    assert metrics["face_eer"]["implied_threshold"] == 0.31
    assert metrics["attribution"]["accuracy"] == 0.9655
    assert metrics["attribution"]["denominator"] == 58


def test_compute_metrics_is_deterministic() -> None:
    a = bench.compute_metrics(eer=_eer_result(), attribution=_attribution_result())
    b = bench.compute_metrics(eer=_eer_result(), attribution=_attribution_result())
    assert a == b


def test_compute_metrics_does_not_mutate_inputs() -> None:
    eer, attribution = _eer_result(), _attribution_result()
    metrics = bench.compute_metrics(eer=eer, attribution=attribution)
    # Mutating the returned sub-dicts must not reach back into the inputs.
    metrics["face_eer"]["eer"] = 999.0
    metrics["attribution"]["denominator"] = -1
    assert eer["eer"] == 0.0421
    assert attribution["denominator"] == 58


# --------------------------------------------------------------------------- #
# format_summary — pure render: headline numbers present, no crash on partials.
# --------------------------------------------------------------------------- #
def test_format_summary_renders_headline_numbers() -> None:
    metrics = bench.compute_metrics(eer=_eer_result(), attribution=_attribution_result())
    metadata = {"run_ts": "2026-06-27T12:00:00Z", "git_sha": "abc123", "seed": 1234}
    out = bench.format_summary(metrics, metadata)
    assert isinstance(out, str)
    assert "0.0421" in out          # EER headline
    assert "0.9655" in out          # attribution accuracy headline
    assert "58" in out              # denominator
    assert "2026-06-27T12:00:00Z" in out


def test_format_summary_tolerates_empty_metrics() -> None:
    # Defensive .get(...) path — a partial dict mid-development must not crash.
    out = bench.format_summary({}, {})
    assert isinstance(out, str)
    assert "SB.7 PERCEPTION BENCH" in out


# --------------------------------------------------------------------------- #
# collect_metadata — config snapshot keys + RECOGNITION_THRESHOLD pin.
# --------------------------------------------------------------------------- #
def test_collect_metadata_has_expected_keys() -> None:
    md = bench.collect_metadata(seed=7, denominator=58, duration_secs=1.234)
    assert set(md) >= {
        "run_ts", "git_sha", "recognition_threshold", "embed_model",
        "seed", "denominator", "duration_secs",
    }
    assert md["seed"] == 7
    assert md["denominator"] == 58
    assert isinstance(md["git_sha"], str)
    # Pins the production config snapshot so a re-baseline review sees a drift.
    assert md["recognition_threshold"] == 0.28
    assert md["duration_secs"] == 1.23


# --------------------------------------------------------------------------- #
# save_run / load round-trip — persistence layer at tmp_path only.
# --------------------------------------------------------------------------- #
def test_save_run_round_trips(tmp_path) -> None:
    metrics = bench.compute_metrics(eer=_eer_result(), attribution=_attribution_result())
    metadata = {"run_ts": "2026-06-27T12:00:00Z", "git_sha": "abc123", "seed": 1234}
    path = bench.save_run(metrics, metadata, out_dir=tmp_path)
    assert path.exists()
    assert path.parent == tmp_path
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["metrics"] == metrics
    assert loaded["metadata"] == metadata


# --------------------------------------------------------------------------- #
# load_baseline — None when absent, dict when present.
# --------------------------------------------------------------------------- #
def test_load_baseline_returns_none_when_absent(tmp_path) -> None:
    assert bench.load_baseline(tmp_path / "nope.json") is None


def test_load_baseline_reads_existing(tmp_path) -> None:
    payload = {"metrics": {"face_eer": {"eer": 0.04}}, "metadata": {"seed": 1}}
    p = tmp_path / "baseline.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    assert bench.load_baseline(p) == payload


# --------------------------------------------------------------------------- #
# Attribution driver (Step 2c) — BUILT: drives the real reconcile over the
# golden cases. The honest-stub assertion flips to a shape + contract lock:
# green CI here ⟺ every golden expected_action matches the production
# reconciler (the deterministic validator the golden source exists to enforce).
# --------------------------------------------------------------------------- #
def test_attribution_driver_returns_canonical_shape() -> None:
    result = bench.compute_attribution_accuracy()
    # Exactly the shape compute_metrics / format_summary read (PI-4).
    assert set(result) == {"accuracy", "per_band", "mismatches", "denominator"}
    # A2 tri-directional denominator lock (Plan v2 §4b, 2026-07-02) — the gate
    # is the RULE (denominator == len(CASES) == the locked count), never a
    # pre-blessed integer hard-coded here:
    #   (i)  adding a structural helper fn to the golden module leaves
    #        len(CASES) unchanged → green;
    #   (ii) adding an N-family negative-invariant test leaves len(CASES)
    #        unchanged → green;
    #   (iii) adding a positive golden case moves len(CASES) AND the bench's
    #        reported denominator TOGETHER — one-not-the-other FAILS here
    #        (and an un-bumped EXPECTED_CASE_COUNT fails at golden import).
    from tests.reconciler_golden import EXPECTED_CASE_COUNT, RECONCILER_GOLDEN_CASES
    assert result["denominator"] == len(RECONCILER_GOLDEN_CASES) == EXPECTED_CASE_COUNT
    assert isinstance(result["accuracy"], float)
    assert 0.0 <= result["accuracy"] <= 1.0
    assert isinstance(result["per_band"], dict)
    assert all(isinstance(v, float) for v in result["per_band"].values())
    assert isinstance(result["mismatches"], list)


def test_attribution_golden_actions_match_reconciler() -> None:
    # Golden-test-first lock: every golden expected_action must equal the real
    # reconciler's decision.action. A drift in either the golden source OR a
    # reconciler rule fails CI here with the offending case(s) named.
    result = bench.compute_attribution_accuracy()
    assert result["mismatches"] == [], (
        f"{len(result['mismatches'])} golden case(s) diverge from reconcile: "
        f"{result['mismatches']}"
    )
    assert result["accuracy"] == 1.0
    # Every band the golden source exercises is fully green.
    assert all(acc == 1.0 for acc in result["per_band"].values())


# --------------------------------------------------------------------------- #
# Face-EER driver (Step 3) — BUILT: enrols the committed synthetic set
# leave-one-out into a real FaceDB (temp dir; production faces/ never touched)
# and drives recognize over the FAISS path. The honest-stub assertion flips to
# shape + A3 (PI-2 lock) + A4 (reproducibility) anchors.
# --------------------------------------------------------------------------- #
_SYNTHETIC_NPZ = pathlib.Path(bench.__file__).resolve().parent / "data" / "synthetic_embeddings.npz"


def test_face_eer_returns_canonical_shape() -> None:
    result = bench.compute_face_eer()
    # Exactly the canonical shape compute_metrics / format_summary /
    # collect_metadata read (PI-4) — mirrors the _eer_result() fixture.
    assert set(result) == {"eer", "implied_threshold", "n_genuine", "n_impostor", "seed"}
    assert isinstance(result["eer"], float) and math.isfinite(result["eer"])
    assert 0.0 <= result["eer"] <= 1.0
    assert isinstance(result["implied_threshold"], float)
    assert math.isfinite(result["implied_threshold"])
    # Counts + seed are rule-gated against the COMMITTED .npz split (never a
    # pre-blessed integer) — a regenerated set moves both sides together.
    import numpy as np

    data = np.load(_SYNTHETIC_NPZ)
    assert result["n_genuine"] == data["genuine_probe_embeddings"].shape[0]
    assert result["n_impostor"] == data["impostor_probe_embeddings"].shape[0]
    assert result["seed"] == int(data["seed"])


def test_face_eer_reproducible_across_runs() -> None:
    # A4 — fixed seed + committed set + exact IndexFlatIP search: two full
    # gallery-build + probe cycles must yield byte-identical results.
    assert bench.compute_face_eer() == bench.compute_face_eer()


def test_face_eer_nondegenerate_on_committed_set() -> None:
    # The committed set is DESIGNED with a controlled genuine/impostor overlap
    # (heterogeneous capture quality + one hard-impostor doppelgänger — see
    # gen_synthetic_embeddings.py). A 0.0 EER would make the bench blind to
    # threshold regressions; ≥0.5 means the separation collapsed. Either way
    # the set (or the recognition path) drifted.
    result = bench.compute_face_eer()
    assert 0.0 < result["eer"] < 0.5
    # The implied threshold must be a plausible cosine acceptance point.
    assert -1.0 < result["implied_threshold"] < 1.0


# --------------------------------------------------------------------------- #
# A3 — the PI-2 structural lock: compute_face_eer drives FaceDB.recognize +
# enrols a real gallery; raw-cosine similarity math is FORBIDDEN anywhere in
# the bench module (the only embedding-similarity math lives inside
# FaceDB.recognize). Forward scan + self-tests route through ONE shared
# detector so the self-tests validate the same detector that guards
# production (#123 PI-1 discipline). Scope: bench.py only — the offline
# generator (gen_synthetic_embeddings.py) legitimately uses numpy math to
# BUILD the committed data and never runs at bench time.
# --------------------------------------------------------------------------- #
_PI2_FORBIDDEN_CALLS = frozenset({"dot", "inner", "matmul", "einsum", "vdot", "tensordot"})


def _pi2_violations(source: str) -> list:
    """Shared A3 detector. Returns [] when the source honors PI-2."""
    tree = ast.parse(source)
    violations: list = []

    fn = next(
        (
            node for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "compute_face_eer"
        ),
        None,
    )
    if fn is None:
        violations.append("compute_face_eer: function not found")
    else:
        called_attrs = {
            node.func.attr
            for node in ast.walk(fn)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        if "recognize" not in called_attrs:
            violations.append(
                "compute_face_eer: no .recognize(...) call — PI-2 requires "
                "driving FaceDB.recognize over the FAISS path"
            )
        if "add_embedding" not in called_attrs:
            violations.append(
                "compute_face_eer: no .add_embedding(...) call — PI-2 requires "
                "enrolling a real gallery"
            )

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = None
            if isinstance(node.func, ast.Attribute):
                name = node.func.attr
            elif isinstance(node.func, ast.Name):
                name = node.func.id
            if name in _PI2_FORBIDDEN_CALLS:
                violations.append(
                    f"line {node.lineno}: forbidden similarity call {name!r} "
                    f"— raw-cosine path (PI-2)"
                )
            elif name is not None and "cosine" in name.lower():
                violations.append(
                    f"line {node.lineno}: forbidden call {name!r} — raw-cosine "
                    f"path (PI-2)"
                )
            elif name == "sum" and _call_touches_mult(node):
                # (a * b).sum() / np.sum(a * b) — the elementwise
                # multiply-then-sum raw-cosine construction (detector
                # blind spot surfaced at Step-3 adversarial review;
                # strengthened same-cycle).
                violations.append(
                    f"line {node.lineno}: sum over an elementwise multiply — "
                    f"raw-cosine construction (PI-2)"
                )
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.MatMult):
            violations.append(
                f"line {node.lineno}: forbidden '@' matrix-multiply — "
                f"raw-cosine path (PI-2)"
            )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if "faiss" in alias.name:
                    violations.append(
                        f"line {node.lineno}: direct faiss import — the bench "
                        f"must go through FaceDB (PI-2)"
                    )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if "faiss" in module:
                violations.append(
                    f"line {node.lineno}: direct faiss import — the bench "
                    f"must go through FaceDB (PI-2)"
                )
            # Alias-evasion: `from numpy import dot as d` renames the callable
            # so the call-site scan can't see it — flag the IMPORT of any
            # forbidden similarity name, whatever it is bound to (2nd blind
            # spot surfaced at Step-3 adversarial review).
            for alias in node.names:
                if alias.name in _PI2_FORBIDDEN_CALLS or "cosine" in alias.name.lower():
                    violations.append(
                        f"line {node.lineno}: imports similarity primitive "
                        f"{alias.name!r} (as {alias.asname or alias.name!r}) — "
                        f"raw-cosine path (PI-2)"
                    )
    return violations


def _call_touches_mult(call: "ast.Call") -> bool:
    """True when a sum(...) call ranges over an elementwise multiply.

    Covers both spellings: ``np.sum(a * b)`` (Mult inside the args) and
    ``(a * b).sum()`` (Mult inside the attribute's value).
    """
    roots: list = list(call.args)
    if isinstance(call.func, ast.Attribute):
        roots.append(call.func.value)
    return any(
        isinstance(sub, ast.BinOp) and isinstance(sub.op, ast.Mult)
        for root in roots
        for sub in ast.walk(root)
    )


def test_a3_face_eer_drives_recognize_never_raw_cosine() -> None:
    source = pathlib.Path(bench.__file__).read_text(encoding="utf-8")
    assert _pi2_violations(source) == []


_PI2_CLEAN_SRC = """
def compute_face_eer(gallery_set=None):
    db = FaceDB(db_path="x", faiss_path="y")
    db.add_embedding("p", vec, source="enrollment", anti_spoof_verdict=True)
    pid, name, score = db.recognize(vec, threshold=-1.0)
    return {"eer": 0.0}
"""

_PI2_RAW_COSINE_SRC = """
import numpy as np
def compute_face_eer(gallery_set=None):
    scores = [float(np.dot(a, b)) for a, b in pairs]
    return {"eer": 0.0}
"""

_PI2_MATMUL_SRC = """
def compute_face_eer(gallery_set=None):
    db = FaceDB(db_path="x", faiss_path="y")
    db.add_embedding("p", vec, source="enrollment", anti_spoof_verdict=True)
    pid, name, score = db.recognize(vec, threshold=-1.0)
    extra = probe @ gallery.T
    return {"eer": 0.0}
"""

_PI2_NO_ENROLL_SRC = """
def compute_face_eer(gallery_set=None):
    pid, name, score = db.recognize(vec, threshold=-1.0)
    return {"eer": 0.0}
"""


def test_a3_detector_clean_source_passes() -> None:
    assert _pi2_violations(_PI2_CLEAN_SRC) == []


def test_a3_detector_flags_raw_cosine_swap() -> None:
    # The architect's A3 deliberate-regression shape: recognize swapped for
    # np.dot → BOTH the missing-recognize and the forbidden-call checks fire.
    violations = _pi2_violations(_PI2_RAW_COSINE_SRC)
    assert any("no .recognize" in v for v in violations)
    assert any("'dot'" in v for v in violations)


def test_a3_detector_flags_matmul_operator() -> None:
    violations = _pi2_violations(_PI2_MATMUL_SRC)
    assert any("'@' matrix-multiply" in v for v in violations)


def test_a3_detector_flags_missing_enrollment() -> None:
    violations = _pi2_violations(_PI2_NO_ENROLL_SRC)
    assert any("no .add_embedding" in v for v in violations)


_PI2_MULT_SUM_SRC = """
def compute_face_eer(gallery_set=None):
    db = FaceDB(db_path="x", faiss_path="y")
    db.add_embedding("p", vec, source="enrollment", anti_spoof_verdict=True)
    pid, name, score = db.recognize(vec, threshold=-1.0)
    s1 = (a * b).sum()
    s2 = np.sum(a * b)
    return {"eer": 0.0}
"""

_PI2_ALIAS_IMPORT_SRC = """
from numpy import dot as _d
def compute_face_eer(gallery_set=None):
    db = FaceDB(db_path="x", faiss_path="y")
    db.add_embedding("p", vec, source="enrollment", anti_spoof_verdict=True)
    pid, name, score = db.recognize(vec, threshold=-1.0)
    extra = _d(a, b)
    return {"eer": 0.0}
"""


def test_a3_detector_flags_elementwise_multiply_sum() -> None:
    # Blind spot surfaced at the Step-3 adversarial review: (a*b).sum() /
    # np.sum(a*b) builds a cosine without any forbidden call name or '@'.
    violations = _pi2_violations(_PI2_MULT_SUM_SRC)
    assert sum("elementwise multiply" in v for v in violations) == 2


def test_a3_detector_flags_alias_imported_similarity() -> None:
    # 2nd blind spot: `from numpy import dot as _d` hides the call name —
    # the import site is flagged instead.
    violations = _pi2_violations(_PI2_ALIAS_IMPORT_SRC)
    assert any("imports similarity primitive 'dot'" in v for v in violations)


# --------------------------------------------------------------------------- #
# CLI end-to-end — Plan v1 acceptance #1: one invocation produces both metrics,
# persists the run JSON, prints the summary. Runs dir monkeypatched to
# tmp_path so the repo tree is never written by a test.
# --------------------------------------------------------------------------- #
def test_main_end_to_end_persists_run_and_prints_summary(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(bench, "_RUNS_DIR", tmp_path)
    rc = bench.main()
    assert rc == 0
    runs = list(tmp_path.glob("perception_*.json"))
    assert len(runs) == 1
    payload = json.loads(runs[0].read_text(encoding="utf-8"))
    assert set(payload["metrics"]) == {"face_eer", "attribution"}
    assert 0.0 <= payload["metrics"]["face_eer"]["eer"] <= 1.0
    assert payload["metrics"]["attribution"]["accuracy"] == 1.0
    out = capsys.readouterr().out
    assert "SB.7 PERCEPTION BENCH" in out
    assert "eer=" in out


# --------------------------------------------------------------------------- #
# Package shape — the architect-named function set is present + importable.
# --------------------------------------------------------------------------- #
def test_bench_exposes_named_function_set() -> None:
    for name in (
        "load_baseline", "compute_metrics", "collect_metadata",
        "save_run", "format_summary", "main",
        "compute_attribution_accuracy", "compute_face_eer",
    ):
        assert callable(getattr(bench, name)), f"bench.{name} missing/not callable"
