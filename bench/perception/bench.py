# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

"""SB.7 perception eval harness — pure metrics layer + CLI (Step 1: skeleton).

Mirrors the proven two-layer shape of ``tests/eval_intent_bench.py``:

  * PURE functions (deterministic, NO I/O) — ``compute_metrics`` structures two
    already-computed metric dicts into the run container; ``format_summary``
    renders them. These are the layer the CI net unit-tests directly.
  * METADATA / PERSISTENCE — ``collect_metadata`` snapshots git SHA + config
    (subprocess + clock, mirroring eval_intent_bench); ``save_run`` /
    ``load_baseline`` are the JSON I/O layer.
  * METRIC DRIVERS — ``compute_attribution_accuracy`` (Step 2, BUILT) drives
    the real ``reconcile`` over ``RECONCILER_GOLDEN_CASES``; ``compute_face_eer``
    (Step 3, BUILT) enrols the committed synthetic set leave-one-out into a real
    ``FaceDB`` and drives ``recognize`` (PI-2: the FAISS path, never raw cosine).
    Both are deliberately impure (they exercise the real perception path) — the
    antithesis of the pure aggregation layer above.

``main()`` runs end-to-end: ``python -m bench.perception`` produces a
deterministic EER + attribution number on the synthetic set and persists the
run JSON (Plan v1 acceptance #1).

Steps 4-6 (this cycle):

  * ``--write-baseline`` (Step 5, D6) writes ``baseline/baseline.json`` from
    the current run; the COMMIT of that file is human-reviewed, never CI-auto.
  * ``--alert`` (Step 6, D3) recomputes both metrics, diffs against the
    committed baseline via ``evaluate_alert``, and exits non-zero past either
    config-driven band — mirroring ``tests/eval_weekly.py --alert`` (the flag
    controls the exit code; the run JSON + summary are produced either way).
  * ``--real-eer`` (Step 4, D1-B) is DEFERRED per Plan v1 §5: the LFW
    fetch/licensing adds CI risk, so the synthetic gate is the SB.7 floor and
    the LFW half lands as a fast-follow. The flag exists and exits 2 with the
    deferral note so nothing mistakes it for a metric run.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import pathlib
import subprocess
import sys
import time

# Make ``core.*`` resolvable when this file is run script-mode (``python
# bench/perception/bench.py``), mirroring eval_intent_bench's repo-root insert.
# Under ``python -m bench.perception`` the repo root is already on sys.path.
_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# --------------------------------------------------------------------------- #
# Paths — all bench-local, never the production data/ or faces/ trees.
# --------------------------------------------------------------------------- #
_BENCH_DIR = pathlib.Path(__file__).resolve().parent
_RUNS_DIR = _BENCH_DIR / "runs"                 # persisted run JSONs (lazy mkdir)
_BASELINE_PATH = _BENCH_DIR / "baseline" / "baseline.json"  # Step 5 commits this
_DATA_DIR = _BENCH_DIR / "data"                 # Step 3 synthetic_embeddings.npz


# --------------------------------------------------------------------------- #
# PURE metrics layer — no I/O, deterministic. Unit-tested directly in CI.
# --------------------------------------------------------------------------- #
def compute_metrics(*, eer: dict, attribution: dict) -> dict:
    """Structure two pre-computed metric dicts into the run-metrics container.

    PURE: no I/O, no clock, no randomness — same inputs always yield the same
    nested dict, and the inputs are never mutated. The two metric *drivers*
    (``compute_face_eer`` / ``compute_attribution_accuracy``) DO traverse the
    real ``FaceDB`` / ``reconcile`` (Steps 3/2); this function only structures
    their already-computed results so the gate (Step 6) and the summary read one
    canonical shape.

    Args:
        eer: the ``compute_face_eer`` result (Step 3) — carries ``eer`` +
            ``implied_threshold`` + the genuine/impostor sample counts + seed.
        attribution: the ``compute_attribution_accuracy`` result (Step 2/2c) —
            carries ``accuracy`` + ``per_band`` + ``mismatches`` + ``denominator``.

    Returns:
        ``{"face_eer": {...}, "attribution": {...}}`` — the two metric dicts
        nested verbatim under stable keys. Shallow-copied so REBINDING keys on
        the returned sub-dicts cannot reach back into the inputs (nested
        structures like ``per_band`` / ``mismatches`` are shared references —
        callers treat metric dicts as read-only).
    """
    return {
        "face_eer": dict(eer),
        "attribution": dict(attribution),
    }


def format_summary(metrics: dict, metadata: dict) -> str:
    """Render a human-readable one-screen summary of a run. PURE (no I/O).

    Defensive ``.get(...)`` throughout so a partial metrics dict (e.g. while
    Step 2 lands before Step 3) formats without crashing rather than KeyError-ing
    mid-development.
    """
    eer = metrics.get("face_eer", {}) or {}
    attribution = metrics.get("attribution", {}) or {}

    lines: list[str] = []
    lines.append("=" * 64)
    lines.append("SB.7 PERCEPTION BENCH")
    lines.append(
        f"  run_ts={metadata.get('run_ts', '?')}  "
        f"git={metadata.get('git_sha', '?')}  "
        f"seed={metadata.get('seed', '?')}"
    )
    lines.append("-" * 64)

    # Face EER (Step 3) — the solidity floor for face recognition.
    lines.append("Face EER (synthetic gallery, leave-one-out via FaceDB.recognize):")
    lines.append(
        f"  eer={_fmt_float(eer.get('eer'))}  "
        f"implied_threshold={_fmt_float(eer.get('implied_threshold'))}  "
        f"genuine={eer.get('n_genuine', '?')}  impostor={eer.get('n_impostor', '?')}"
    )

    # Attribution accuracy (Step 2) — reconciler routing correctness.
    lines.append("Attribution accuracy (RECONCILER_GOLDEN_CASES via reconcile):")
    lines.append(
        f"  accuracy={_fmt_float(attribution.get('accuracy'))}  "
        f"denominator={attribution.get('denominator', '?')}  "
        f"mismatches={len(attribution.get('mismatches', []) or [])}"
    )
    per_band = attribution.get("per_band") or {}
    if per_band:
        lines.append("  per_band:")
        for band in sorted(per_band):
            lines.append(f"    {band}: {_fmt_float(per_band[band])}")

    lines.append("=" * 64)
    return "\n".join(lines)


def _fmt_float(value: "float | None") -> str:
    """Format a metric float to 4 dp, or ``?`` when absent. PURE helper."""
    if value is None:
        return "?"
    try:
        return f"{float(value):.4f}"
    except (TypeError, ValueError):
        return str(value)


# --------------------------------------------------------------------------- #
# METADATA — git SHA + config snapshot (subprocess + clock; mirrors eval).
# --------------------------------------------------------------------------- #
def _git_sha() -> str:
    """Best-effort ``git rev-parse HEAD``; ``"no-git"`` on any failure.

    Mirrors ``tests/eval_intent_bench._git_sha`` — a bench run should record
    provenance when it can and degrade quietly when git is unavailable.
    """
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=5.0,
        )
        sha = out.stdout.strip()
        return sha if sha else "no-git"
    except Exception:
        return "no-git"


def collect_metadata(*, seed=None, denominator=None, duration_secs=0.0) -> dict:
    """Snapshot the exact config + provenance producing a run.

    Pins ``RECOGNITION_THRESHOLD`` + ``EMBED_MODEL`` from ``core.config`` so a
    re-baseline review can see whether a metric shift rode a config change. The
    git subprocess + UTC clock are the one I/O surface here (exactly mirroring
    eval_intent_bench's ``collect_metadata``); the pure metric math lives in
    ``compute_metrics`` / ``format_summary``.
    """
    from core.config import RECOGNITION_THRESHOLD, EMBED_MODEL

    run_ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "run_ts": run_ts,
        "git_sha": _git_sha(),
        "recognition_threshold": RECOGNITION_THRESHOLD,
        "embed_model": EMBED_MODEL,
        "seed": seed,
        "denominator": denominator,
        "duration_secs": round(float(duration_secs), 2),
    }


# --------------------------------------------------------------------------- #
# PERSISTENCE — run JSON + committed baseline.
# --------------------------------------------------------------------------- #
def save_run(metrics: dict, metadata: dict, *, out_dir: "pathlib.Path | None" = None) -> pathlib.Path:
    """Persist a ``{metrics, metadata}`` run JSON; return the written path.

    Filename derives from ``metadata['run_ts']`` (mirrors eval_intent_bench's
    ``save_run``). The output dir is created lazily so the repo carries no empty
    ``runs/`` placeholder.
    """
    out_dir = out_dir if out_dir is not None else _RUNS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    run_ts = metadata.get("run_ts", "unknown")
    stamp = run_ts.replace("-", "").replace("T", "_").replace(":", "").rstrip("Z")
    path = out_dir / f"perception_{stamp}.json"
    path.write_text(
        json.dumps({"metrics": metrics, "metadata": metadata}, indent=2),
        encoding="utf-8",
    )
    return path


def load_baseline(path: "pathlib.Path | None" = None) -> "dict | None":
    """Load the committed baseline JSON, or ``None`` when it is absent.

    Step 5 commits ``baseline/baseline.json``; until then (and in any env where
    it is missing) this returns ``None`` and the Step-6 gate treats the run as
    baseline-establishing rather than regression-checking.
    """
    path = path if path is not None else _BASELINE_PATH
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_baseline(metrics: dict, metadata: dict, *, path: "pathlib.Path | None" = None) -> pathlib.Path:
    """Write the baseline JSON (Step 5, D6); return the written path.

    Same ``{metrics, metadata}`` payload shape as ``save_run`` so
    ``load_baseline`` round-trips it identically (A6). This writer exists so
    the committed artifact is always regenerated by the SAME code path the
    bench uses — never hand-edited. It is invoked via ``--write-baseline``
    only; re-baselining is an explicit HUMAN-REVIEWED commit (D6), never a
    default-run or CI side effect.
    """
    path = path if path is not None else _BASELINE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"metrics": metrics, "metadata": metadata}, indent=2),
        encoding="utf-8",
    )
    return path


# --------------------------------------------------------------------------- #
# REGRESSION GATE — Step 6 (D3). Mirrors eval_weekly's --alert: the gate
# evaluation is a pure predicate over (fresh metrics, committed baseline);
# the CLI flag only controls the exit code, never the report substance.
# --------------------------------------------------------------------------- #
def evaluate_alert(
    metrics: dict,
    baseline: "dict | None",
    *,
    eer_band: "float | None" = None,
    attribution_drop_pp: "float | None" = None,
) -> dict:
    """Step-6 (D3) regression gate: diff a fresh run against the baseline.

    Trip predicate (Plan v1 §1 step 6)::

        eer_rise >= PERCEPTION_EER_REGRESSION_BAND
        OR attribution_drop_pp >= PERCEPTION_ATTRIBUTION_DROP_PP

    Bands default to the ``core.config`` constants (config-driven per D3;
    the ``>=2pp`` attribution floor lives there) and are overridable per-call
    for the A5 parametrized tests. Signs: ``eer_rise`` positive = worse
    (EER went up); ``attribution_drop_pp`` positive = worse (accuracy went
    down, in percentage points). Improvements are negative and never trip.

    ``baseline is None`` (file absent — the expected pre-Step-5 state) means
    the run is baseline-ESTABLISHING, not regression-checking (matches the
    ``load_baseline`` contract): never trips, the reason says so. A PRESENT
    baseline missing either metric is corruption, not absence — that arm
    FAILS CLOSED (trips with a malformed-baseline reason) so a truncated
    baseline can't silently disable the gate.

    PURE given explicit bands — no I/O, no clock; the config import is the
    only lookup and happens once per call when the defaults are used.
    """
    if eer_band is None or attribution_drop_pp is None:
        from core.config import (
            PERCEPTION_ATTRIBUTION_DROP_PP,
            PERCEPTION_EER_REGRESSION_BAND,
        )
        if eer_band is None:
            eer_band = float(PERCEPTION_EER_REGRESSION_BAND)
        if attribution_drop_pp is None:
            attribution_drop_pp = float(PERCEPTION_ATTRIBUTION_DROP_PP)

    result: dict = {
        "tripped": False,
        "reasons": [],
        "eer_rise": None,
        "attribution_drop_pp": None,
        "eer_band": eer_band,
        "attribution_band_pp": attribution_drop_pp,
    }

    if baseline is None:
        result["reasons"].append(
            "no committed baseline — run treated as baseline-establishing, "
            "not regression-checking (establish one via --write-baseline + "
            "human-reviewed commit)"
        )
        return result

    base_metrics = baseline.get("metrics", {}) or {}
    base_eer = (base_metrics.get("face_eer", {}) or {}).get("eer")
    base_acc = (base_metrics.get("attribution", {}) or {}).get("accuracy")
    cur_eer = (metrics.get("face_eer", {}) or {}).get("eer")
    cur_acc = (metrics.get("attribution", {}) or {}).get("accuracy")

    if base_eer is None or cur_eer is None:
        result["tripped"] = True
        result["reasons"].append(
            "malformed baseline or run: metrics.face_eer.eer missing — "
            "failing CLOSED (a truncated baseline must not disable the gate)"
        )
    else:
        eer_rise = float(cur_eer) - float(base_eer)
        result["eer_rise"] = eer_rise
        if eer_rise >= eer_band:
            result["tripped"] = True
            result["reasons"].append(
                f"EER regression: {float(cur_eer):.4f} vs baseline "
                f"{float(base_eer):.4f} (rise {eer_rise:+.4f} >= band {eer_band:.4f})"
            )

    if base_acc is None or cur_acc is None:
        result["tripped"] = True
        result["reasons"].append(
            "malformed baseline or run: metrics.attribution.accuracy missing — "
            "failing CLOSED (a truncated baseline must not disable the gate)"
        )
    else:
        drop_pp = (float(base_acc) - float(cur_acc)) * 100.0
        result["attribution_drop_pp"] = drop_pp
        if drop_pp >= attribution_drop_pp:
            result["tripped"] = True
            result["reasons"].append(
                f"attribution regression: {float(cur_acc):.4f} vs baseline "
                f"{float(base_acc):.4f} (drop {drop_pp:+.2f}pp >= band "
                f"{attribution_drop_pp:.2f}pp)"
            )

    return result


# --------------------------------------------------------------------------- #
# METRIC DRIVERS — Steps 2 & 3 (both BUILT). These traverse the real perception
# path (impure by design): Step 2c drives ``reconcile`` over the golden cases;
# Step 3 drives ``FaceDB.recognize`` over the committed synthetic set (PI-2).
# --------------------------------------------------------------------------- #
def compute_attribution_accuracy(*_args, **_kwargs) -> dict:
    """Attribution metric (Step 2c) — drive the REAL ``reconcile`` over the golden cases.

    Impure by design: it constructs the channel/state dataclasses
    (``IdentityClaim`` / ``PresenceState`` / ``SessionState``) from each golden
    case's dict payloads and runs the production ``reconcile`` cascade. The
    channel imports are deliberately local to this driver — the golden module
    (``tests/reconciler_golden.py``) imports nothing beyond ``core.config`` at
    load time (PI-3: single source, no channel deps in the data file).

    For each ``ReconcilerGoldenCase`` it compares ``decision.action`` against
    ``case.expected_action`` (action-only — the deterministic validator that
    catches a wrong ``expected_action`` long before the 2b full-suite re-point
    catches a wrong rule/pid). Results bucket by ``case.expected_band`` so a
    band-localised regression (e.g. the gap-band watch) surfaces in ``per_band``.

    Returns the exact shape ``compute_metrics`` / ``format_summary`` read
    (PI-4)::

        {
            "accuracy": correct / denominator,       # overall, [0.0, 1.0]
            "per_band": {band: band_accuracy, ...},  # per expected_band
            "mismatches": [{case_id, band, expected_action, got_action,
                            rule_fired}, ...],        # only the failures
            "denominator": len(RECONCILER_GOLDEN_CASES),
        }
    """
    # Channel/state imports live HERE (the impure driver), never at golden-module
    # load. PI-3: RECONCILER_GOLDEN_CASES is the single source of truth.
    from core.reconciler import reconcile
    from core.reconciler_state import SessionState
    from core.vision_channel import PresenceState
    from core.voice_channel import IdentityClaim

    from tests.reconciler_golden import RECONCILER_GOLDEN_CASES

    # band -> [correct, total]; computed alongside the overall tally so per_band
    # and accuracy never diverge (same single pass over the cases).
    band_tally: "dict[str, list[int]]" = {}
    mismatches: "list[dict]" = []
    correct = 0

    for case in RECONCILER_GOLDEN_CASES:
        claim = IdentityClaim(**case.claim)
        presence = PresenceState(**case.presence)
        session = SessionState(**case.session)

        decision = reconcile(claim, presence, session)
        got = decision.action
        ok = got == case.expected_action

        bucket = band_tally.setdefault(case.expected_band, [0, 0])
        bucket[1] += 1
        if ok:
            correct += 1
            bucket[0] += 1
        else:
            mismatches.append(
                {
                    "case_id": case.case_id,
                    "band": case.expected_band,
                    "expected_action": case.expected_action,
                    "got_action": got,
                    "rule_fired": decision.rule_fired,
                }
            )

    denominator = len(RECONCILER_GOLDEN_CASES)
    accuracy = correct / denominator if denominator else 0.0
    per_band = {
        band: (c / t if t else 0.0) for band, (c, t) in band_tally.items()
    }
    return {
        "accuracy": accuracy,
        "per_band": per_band,
        "mismatches": mismatches,
        "denominator": denominator,
    }


def _eer_from_scores(genuine_scores: list, impostor_scores: list) -> "tuple[float, float]":
    """EER + implied threshold from two score distributions. PURE (no I/O).

    Sweeps every observed score (plus one above-max sentinel so the
    FAR=0/FRR=1 endpoint exists) as a candidate acceptance threshold ``t``:
    ``FAR(t) = mean(impostor >= t)``, ``FRR(t) = mean(genuine < t)``. Returns
    ``((FAR + FRR) / 2, t)`` at the candidate minimizing ``|FAR - FRR|``.
    Deterministic tie-break: candidates ascend, strict ``<`` keeps the first
    (lowest) minimizing threshold. Operates ONLY on already-collected score
    floats — the embedding-similarity math lives inside ``FaceDB.recognize``
    (PI-2: no raw cosine in this module).
    """
    if not genuine_scores or not impostor_scores:
        raise ValueError(
            "EER needs non-empty genuine AND impostor score distributions "
            f"(got {len(genuine_scores)} genuine / {len(impostor_scores)} impostor)"
        )
    candidates = sorted(set(genuine_scores) | set(impostor_scores))
    candidates.append(candidates[-1] + 1.0)  # above-max: FAR=0, FRR=1

    best_gap: "float | None" = None
    best_eer = 0.0
    best_threshold = 0.0
    n_imp = float(len(impostor_scores))
    n_gen = float(len(genuine_scores))
    for t in candidates:
        far = sum(1 for s in impostor_scores if s >= t) / n_imp
        frr = sum(1 for s in genuine_scores if s < t) / n_gen
        gap = abs(far - frr)
        if best_gap is None or gap < best_gap:
            best_gap = gap
            best_eer = (far + frr) / 2.0
            best_threshold = t
    return best_eer, best_threshold


def compute_face_eer(gallery_set: "pathlib.Path | str | None" = None) -> dict:
    """Face-EER metric (Step 3, PI-2) — drive the REAL ``FaceDB.recognize``.

    Enrols the committed synthetic set leave-one-out into a real ``FaceDB``
    living in a throwaway temp dir (db_path + faiss_path both injected — the
    production ``faces/`` tree is never touched, including the FAISS dirty
    sentinel which derives from the injected faiss_path), then drives every
    probe through ``recognize`` — the full production path: L2-normalize →
    FAISS IndexFlatIP search → idx→person map → persons-table name lookup.

    Leave-one-out semantics (PI-2, Plan v1 §"decision matrix"):

    * **genuine** probe — its identity IS enrolled (5 gallery embeddings),
      but the probe embedding itself never is.
    * **impostor** probe — its identity is NOT enrolled at all.

    ``recognize`` is called with ``threshold=-1.0`` so every probe returns
    both the best-match pid AND the raw FAISS score: production treats the
    threshold as a caller parameter (``RECOGNITION_THRESHOLD`` /
    ``adaptive_threshold``), and the sweep over candidate thresholds IS this
    metric's job — it produces ``implied_threshold`` to compare against the
    production setting. **No raw cosine anywhere in this module** — the only
    similarity math is inside ``FaceDB.recognize`` (A3 locks this shape).

    A genuine probe whose best match is the WRONG identity is scored ``-1.0``
    (below every realizable cosine → contributes FRR at every threshold above
    ``-1.0``, and the ``-1.0`` candidate itself can never win the sweep since
    FAR=1.0 there): a
    misidentification is a recognition failure and must push EER up, not
    silently count its wrong-person score as genuine. The committed set
    yields zero misidentifications at freeze time; drift here surfaces
    through the EER metric and the Step-6 alert gate, not a crash.

    Enrollment failures (diversity gate, anti-spoof catch-all, cap) raise
    ``RuntimeError`` — a partially-enrolled gallery would silently deflate
    genuine scores, so the bench fails LOUD instead of computing a
    plausible-but-wrong EER.

    SB.5 enrollment-gate interaction (Step 7 matrix, D4): FaceDB's
    ``add_person``/``add_embedding`` are gated on
    ``config.ENROLLMENT_MODE == "persistent"`` — under a profile that
    declares otherwise (robotics: ``none``) every gallery write would be
    refused and the bench would fail loud. That gate protects PERSONAL
    biometric persistence; this gallery is committed SYNTHETIC data enrolled
    into a throwaway temp-dir FaceDB deleted on exit, and the metric
    measures the profile-independent engine recognition path. So the bench
    forces ``persistent`` for the DURATION OF ITS OWN TEMP DB ONLY
    (try/finally-restored), keeping ``--alert`` runnable under every
    profile leg of the slow.yml matrix.

    Returns the canonical shape (PI-4)::

        {"eer": float, "implied_threshold": float,
         "n_genuine": int, "n_impostor": int, "seed": int}
    """
    import tempfile

    import numpy as np

    from core import config as _cfg
    from core.db import FaceDB

    npz_path = (
        pathlib.Path(gallery_set) if gallery_set is not None
        else _DATA_DIR / "synthetic_embeddings.npz"
    )
    data = np.load(npz_path)
    seed = int(data["seed"])
    gallery_embeddings = data["gallery_embeddings"]
    gallery_person = data["gallery_person"]
    genuine_embeddings = data["genuine_probe_embeddings"]
    genuine_person = data["genuine_probe_person"]
    impostor_embeddings = data["impostor_probe_embeddings"]

    def _pid(identity_idx: "int | np.integer") -> str:
        return f"synth_{int(identity_idx):02d}"

    # SB.5 × Step-7 matrix: force "persistent" for the bench-local throwaway
    # DB only (rationale in the docstring); restored whatever the profile set.
    _prior_enrollment_mode = _cfg.ENROLLMENT_MODE
    _cfg.ENROLLMENT_MODE = "persistent"
    try:
        with tempfile.TemporaryDirectory(prefix="sb7_eer_gallery_") as tmp:
            tmp_dir = pathlib.Path(tmp)
            db = FaceDB(
                db_path=str(tmp_dir / "bench_faces.db"),
                faiss_path=tmp_dir / "bench_faiss.index",
            )
            try:
                for identity_idx in sorted({int(i) for i in gallery_person}):
                    db.add_person(_pid(identity_idx), f"Synth {identity_idx:02d}",
                                  person_type="known")
                for vec, identity_idx in zip(gallery_embeddings, gallery_person):
                    stored = db.add_embedding(
                        _pid(identity_idx), vec, source="enrollment",
                        anti_spoof_verdict=True,
                    )
                    if not stored:
                        raise RuntimeError(
                            f"synthetic gallery enrollment rejected for "
                            f"{_pid(identity_idx)} — a partial gallery would "
                            f"silently skew the EER; check the diversity gate / "
                            f"anti-spoof catch-all"
                        )

                genuine_scores: "list[float]" = []
                for vec, identity_idx in zip(genuine_embeddings, genuine_person):
                    got_pid, _name, score = db.recognize(vec, threshold=-1.0)
                    genuine_scores.append(
                        float(score) if got_pid == _pid(identity_idx) else -1.0
                    )
                impostor_scores = [
                    float(db.recognize(vec, threshold=-1.0)[2])
                    for vec in impostor_embeddings
                ]
            finally:
                db.close()
    finally:
        _cfg.ENROLLMENT_MODE = _prior_enrollment_mode

    eer, implied_threshold = _eer_from_scores(genuine_scores, impostor_scores)
    return {
        "eer": eer,
        "implied_threshold": implied_threshold,
        "n_genuine": len(genuine_scores),
        "n_impostor": len(impostor_scores),
        "seed": seed,
    }


# --------------------------------------------------------------------------- #
# CLI — end-to-end: both drivers live, one invocation → metrics + run JSON.
# Steps 4-6 flags: --real-eer (deferred, exit 2) / --write-baseline / --alert.
# --------------------------------------------------------------------------- #
_REAL_EER_DEFERRAL_MSG = (
    "--real-eer (Step 4, D1-B LFW mode) is DEFERRED per Plan v1 §5: the LFW "
    "dataset fetch + licensing review add CI risk, so the synthetic gate is "
    "the SB.7 floor and the LFW real-EER half lands as a fast-follow. See "
    "karaos-org-discussions/solidify-base/SB7-1-plan-v1.md §5 (deferral "
    "sanctioned; developer's call at Pass-3)."
)


def main(argv: "list[str] | None" = None) -> int:
    """Run the synthetic-set bench: compute → structure → persist → print.

    Both metric drivers are live (Steps 2c + 3): one invocation produces a
    deterministic EER + attribution number on the committed synthetic set,
    persists the run JSON under ``runs/``, and prints the summary.

    Flags (Steps 4-6):

    ``--real-eer``
        Step 4 (D1-B): DEFERRED per Plan v1 §5 — prints the deferral note to
        stderr and exits 2 BEFORE any computation (a deferral must never be
        mistakable for a successful metric run).
    ``--write-baseline``
        Step 5 (D6): additionally writes ``baseline/baseline.json`` from this
        run via ``write_baseline``. The git commit stays human-reviewed.
    ``--alert``
        Step 6 (D3): evaluates ``evaluate_alert`` against the committed
        baseline and returns 1 when the gate trips (mirrors
        ``eval_weekly --alert`` — the flag controls ONLY the exit code; the
        run JSON + summary are produced regardless).

    ``argv=None`` (library/test call) means "no flags"; the script entry
    points pass ``sys.argv[1:]`` explicitly, so pytest's own argv can never
    leak into the parser.
    """
    parser = argparse.ArgumentParser(
        prog="bench.perception",
        description="SB.7 perception eval harness (EER + attribution on the "
                    "committed synthetic set).",
    )
    parser.add_argument(
        "--real-eer", action="store_true",
        help="LFW real-EER mode — DEFERRED per Plan v1 §5 (exits 2).",
    )
    parser.add_argument(
        "--write-baseline", action="store_true",
        help="Also write baseline/baseline.json from this run (Step 5, D6).",
    )
    parser.add_argument(
        "--alert", action="store_true",
        help="Exit non-zero if this run regresses past the D3 bands vs the "
             "committed baseline (Step 6).",
    )
    args = parser.parse_args(argv if argv is not None else [])

    if args.real_eer:
        print(_REAL_EER_DEFERRAL_MSG, file=sys.stderr)
        return 2

    t0 = time.time()
    attribution = compute_attribution_accuracy()          # Step 2
    eer = compute_face_eer()                               # Step 3
    metrics = compute_metrics(eer=eer, attribution=attribution)
    metadata = collect_metadata(
        seed=eer.get("seed"),
        denominator=attribution.get("denominator"),
        duration_secs=time.time() - t0,
    )
    save_run(metrics, metadata)
    print(format_summary(metrics, metadata))

    if args.write_baseline:
        baseline_path = write_baseline(metrics, metadata)
        print(
            f"[bench.perception] baseline written: {baseline_path} "
            f"(D6: the git commit of this file stays human-reviewed)"
        )

    if args.alert:
        verdict = evaluate_alert(metrics, load_baseline())
        for reason in verdict["reasons"]:
            print(f"[bench.perception] alert: {reason}")
        if verdict["tripped"]:
            print("[bench.perception] ALERT — regression gate TRIPPED (exit 1)")
            return 1
        print(
            f"[bench.perception] alert gate clean — "
            f"eer_rise={_fmt_float(verdict['eer_rise'])} "
            f"(band {verdict['eer_band']:.4f}), "
            f"attribution_drop_pp={_fmt_float(verdict['attribution_drop_pp'])} "
            f"(band {verdict['attribution_band_pp']:.2f}pp)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
