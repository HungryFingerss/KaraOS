# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

"""``bench.perception`` — SB.7 perception eval harness.

Turns "is the robot still good at seeing and hearing?" from a vibe into two
CI-enforced numbers:

- **face-EER** — speaker-independent face-recognition solidity, measured by
  enrolling a synthetic gallery leave-one-out into a *real* ``FaceDB`` and
  driving ``recognize`` (PI-2: the FAISS path, never a raw cosine shortcut).
- **attribution accuracy** — reconciler routing correctness, measured by driving
  the *real* ``reconcile`` over the single-source ``RECONCILER_GOLDEN_CASES``
  (PI-3) at the parametrize-expanded ``len(CASES)`` denominator (PI-4).

The implementation lives in :mod:`bench.perception.bench`. Run on demand with
``python -m bench.perception``; gate it in ``slow.yml`` via ``--alert``.
"""
