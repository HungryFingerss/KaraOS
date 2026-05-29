"""
Zero-import module holding constants shared between pipeline.py and the
structural-invariant tests in tests/test_*_invariant.py.

Why this module exists separately:
- Importing pipeline.py at test-collection time triggers torchaudio /
  pyannote / ONNX side effects that crash on Windows dev machines.
- pipeline.py also runs top-level setup (log archival, daemon thread starts,
  signal handlers) that has no business firing during a static AST scan.
- This module is the agreed-upon "single source of truth" for invariants
  that pipeline.py enforces at runtime AND tests verify at scan time.

Add new invariant constants here as they're introduced. Both pipeline.py and
the corresponding test import from here. Do NOT define them in pipeline.py
and re-export — that defeats the whole point.

Reserved for future invariants:
    DISPUTED_LITERAL_ALLOWLIST_FILES (P0.1 sister-test scope expansion)
    SESSION_REQUIRED_FIELDS          (P0.7 schema invariant)
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

# P0.13 — repeat-tool-guard.
REPEAT_GUARD_FIELDS: frozenset[str] = frozenset({
    "_tool_repeat_last",
    "_tool_repeat_count",
})

ALLOWED_REPEAT_GUARD_FUNCS: frozenset[str] = frozenset({
    "_execute_tool",
    # When _execute_tool is decomposed (P1.A3), add each helper that
    # legitimately resets the guard. Each addition is a deliberate decision:
    # is this helper part of the repeat-guard safety boundary?
})
