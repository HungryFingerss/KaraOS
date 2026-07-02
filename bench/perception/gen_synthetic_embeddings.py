# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

"""SB.7 Step 3 — one-shot generator for the committed synthetic EER set.

Writes ``bench/perception/data/synthetic_embeddings.npz`` — the fixed-seed
synthetic gallery/probe set that ``compute_face_eer`` (PI-2) enrols into a real
``FaceDB`` and drives through ``recognize``. The **committed .npz is the
authoritative artifact**; this script is provenance — it documents exactly how
the arrays were produced. Regeneration on the SAME numpy version + platform
reproduces the arrays; across numpy feature releases or BLAS/platforms the
floats may differ in the last bits (numpy guarantees BitGenerator stream
stability, not distribution-method or downstream float-op stability) — which
is exactly why the .npz is committed and the bench NEVER regenerates it. This
script runs OFFLINE, once, by hand — never at bench time, never in CI.

Set design (developer Pass-3 grounding, per Plan v1 §"left for developer":
N identities, K per identity, and the genuine/impostor separation that yields
a NON-degenerate EER):

* ``N_ENROLLED = 16`` identities, ``K_GALLERY + K_PROBE = 5 + 5`` embeddings
  each. The 5 gallery embeddings enrol (5 == ``N_INITIAL_FACE`` — the
  diversity gate never engages); the 5 probes are the leave-one-out genuine
  trials (their identity IS enrolled; the probe embedding itself never is).
  → ``n_genuine = 80``.
* ``N_IMPOSTOR_EASY = 9`` + ``N_IMPOSTOR_HARD = 1`` identities, 8 probes each,
  NEVER enrolled. → ``n_impostor = 80``.
* Per-identity embeddings = unit-normalized ``centroid + sigma·N(0, I)`` where
  ``sigma`` is derived from a per-identity "capture quality" ``q`` (the
  expected cosine of an embedding to its own centroid):
  ``sigma = sqrt((1/q² − 1) / DIM)``.
* **Heterogeneous quality** ``q ~ U(0.66, 0.88)`` per enrolled identity models
  the real capture-condition spread — low-quality identities produce the
  genuine LOW tail (probe-vs-gallery best-match down to ~0.45).
* The single **hard impostor** centroid is a mix of a random enrolled centroid
  ``c`` and an orthogonal direction: ``normalize(β·c + sqrt(1−β²)·u_perp)``
  with ``β ~ U(0.78, 0.88)`` — a doppelgänger whose probes score ~0.45-0.55
  against the target's gallery, overlapping the genuine low tail. Easy
  impostors are independent random unit vectors (near-orthogonal in 512-dim,
  scores ≈ 0).

The overlap band (~[0.45, 0.55]) is BROAD by design, not knife-edge: measured
through the real FaceDB path at freeze time this yields EER = 0.0625 with
implied_threshold ≈ 0.51 and zero genuine misidentifications. A degenerate
0.0 EER would make the bench blind to threshold regressions; the anchor
``test_face_eer_nondegenerate_on_committed_set`` pins non-degeneracy.

.npz payload::

    gallery_embeddings        float32 [80, 512]   L2-normalized
    gallery_person            int32   [80]        identity index 0..15
    genuine_probe_embeddings  float32 [80, 512]
    genuine_probe_person      int32   [80]
    impostor_probe_embeddings float32 [80, 512]   identities never enrolled
    seed                      int64   scalar      the generator seed
    dim                       int64   scalar      512 (== config.EMBEDDING_DIM)

Regenerate with::

    python -m bench.perception.gen_synthetic_embeddings

Any regeneration that changes the arrays is a DATA CHANGE — the committed
baseline (Step 5) must be re-established and the change called out in review.
"""

from __future__ import annotations

import math
import pathlib

import numpy as np

SEED = 20260702
DIM = 512                    # == core.config.EMBEDDING_DIM (AdaFace IR101)

N_ENROLLED = 16
K_GALLERY = 5                # == N_INITIAL_FACE — diversity gate bypassed
K_PROBE = 5

N_IMPOSTOR_EASY = 9
N_IMPOSTOR_HARD = 1
K_IMPOSTOR = 8

QUALITY_LO, QUALITY_HI = 0.66, 0.88   # per-enrolled-identity capture quality
IMPOSTOR_QUALITY = 0.82               # impostor intra-class quality (fixed)
BETA_LO, BETA_HI = 0.78, 0.88         # hard-impostor centroid mix coefficient

_OUT_PATH = pathlib.Path(__file__).resolve().parent / "data" / "synthetic_embeddings.npz"


def _unit(v: np.ndarray) -> np.ndarray:
    return v / np.linalg.norm(v)


def _noisy_embeddings(rng: np.random.Generator, centroid: np.ndarray,
                      quality: float, n: int) -> np.ndarray:
    """n unit vectors with expected cosine ~``quality`` to ``centroid``."""
    sigma = math.sqrt((1.0 / (quality * quality) - 1.0) / DIM)
    return np.stack(
        [_unit(centroid + sigma * rng.standard_normal(DIM)) for _ in range(n)]
    ).astype(np.float32)


def build_arrays(seed: int = SEED) -> dict:
    """Build the full array payload. Deterministic for a given seed."""
    rng = np.random.default_rng(seed)

    centroids = [_unit(rng.standard_normal(DIM)) for _ in range(N_ENROLLED)]
    qualities = rng.uniform(QUALITY_LO, QUALITY_HI, size=N_ENROLLED)

    gallery_vecs: list[np.ndarray] = []
    gallery_person: list[int] = []
    genuine_vecs: list[np.ndarray] = []
    genuine_person: list[int] = []
    for i, (centroid, quality) in enumerate(zip(centroids, qualities)):
        embs = _noisy_embeddings(rng, centroid, float(quality), K_GALLERY + K_PROBE)
        gallery_vecs.append(embs[:K_GALLERY])
        gallery_person += [i] * K_GALLERY
        genuine_vecs.append(embs[K_GALLERY:])
        genuine_person += [i] * K_PROBE

    impostor_vecs: list[np.ndarray] = []
    for _ in range(N_IMPOSTOR_EASY):
        centroid = _unit(rng.standard_normal(DIM))
        impostor_vecs.append(
            _noisy_embeddings(rng, centroid, IMPOSTOR_QUALITY, K_IMPOSTOR)
        )
    for _ in range(N_IMPOSTOR_HARD):
        base = centroids[int(rng.integers(0, N_ENROLLED))]
        beta = float(rng.uniform(BETA_LO, BETA_HI))
        perp = rng.standard_normal(DIM)
        perp = _unit(perp - np.dot(perp, base) * base)
        centroid = _unit(beta * base + math.sqrt(1.0 - beta * beta) * perp)
        impostor_vecs.append(
            _noisy_embeddings(rng, centroid, IMPOSTOR_QUALITY, K_IMPOSTOR)
        )

    return {
        "gallery_embeddings": np.vstack(gallery_vecs),
        "gallery_person": np.array(gallery_person, dtype=np.int32),
        "genuine_probe_embeddings": np.vstack(genuine_vecs),
        "genuine_probe_person": np.array(genuine_person, dtype=np.int32),
        "impostor_probe_embeddings": np.vstack(impostor_vecs),
        "seed": np.int64(seed),
        "dim": np.int64(DIM),
    }


def main() -> int:
    arrays = build_arrays()
    _OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    np.savez(_OUT_PATH, **arrays)
    print(
        f"[gen_synthetic_embeddings] wrote {_OUT_PATH} — "
        f"gallery={arrays['gallery_embeddings'].shape} "
        f"genuine={arrays['genuine_probe_embeddings'].shape} "
        f"impostor={arrays['impostor_probe_embeddings'].shape} seed={SEED}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
