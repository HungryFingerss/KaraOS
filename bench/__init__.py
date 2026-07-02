# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

"""``bench`` — KaraOS benchmark harnesses.

Each subpackage owns one measurable solidity dimension. The first is
``bench.perception`` (SB.7) — face-EER + speaker-attribution accuracy, a
committed baseline, and a CI regression gate. Benches are NOT test files
(pytest collects ``test_*.py`` only); they are run on demand via
``python -m bench.<name>`` and gated in ``slow.yml``.
"""
