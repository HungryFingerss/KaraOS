"""Bundle 5 D3 (MF7) — AST invariant: no exact `== 0.0` / `!= 0.0` against
`claim.confidence` in core/reconciler.py.

Rationale (Pre-P1 Bundle 5 MF7): the voice-ID backend signals "no usable
signal" via `IdentityClaim.confidence_is_no_signal`, NOT via the ECAPA
exact-0.0 convention. Reconciler rule predicates that test `claim.confidence
== 0.0` (or `!= 0.0`) couple the routing logic to that fragile convention and
silently mis-route the common NEGATIVE-cosine case (anti-correlated speakers).
Predicates MUST use the flag. Genuine threshold comparisons (`<`, `<=`, `>`,
`>=` against a routing constant OR against `0.0` for the Session-119
negative-cosine catch at the pyannote-vouched-stranger rule) are ALLOWED.

Detector: AST-walk core/reconciler.py; reject any `ast.Compare` pairing a
`.confidence` attribute access with a `0.0` literal under `ast.Eq` OR
`ast.NotEq`. Allow `ast.Lt` / `ast.LtE` / `ast.Gt` / `ast.GtE`.

Self-tests: forward (synthetic `== 0.0` AND synthetic `!= 0.0` both fire) +
inverse (flag-based predicate + `< 0.0` threshold both pass).
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RECONCILER_PATH = REPO_ROOT / "core" / "reconciler.py"


def _is_confidence_attr(node: ast.AST) -> bool:
    """True iff node is a `.confidence` attribute access (e.g. claim.confidence)."""
    return isinstance(node, ast.Attribute) and node.attr == "confidence"


def _is_zero_literal(node: ast.AST) -> bool:
    """True iff node is a numeric 0 literal (int 0 or float 0.0), excluding bool."""
    return (
        isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
        and node.value == 0
    )


def find_exact_equality_violations(source: str) -> list[tuple[int, str]]:
    """Return [(lineno, snippet)] for each `claim.confidence ==/!= 0.0` comparison.

    Handles both operand orderings and chained comparisons. Only `Eq`/`NotEq`
    against a 0-literal where the other operand is a `.confidence` attribute
    are violations; `Lt`/`LtE`/`Gt`/`GtE` are allowed (genuine thresholds).
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    violations: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        operands = [node.left, *node.comparators]
        for i, op in enumerate(node.ops):
            if not isinstance(op, (ast.Eq, ast.NotEq)):
                continue
            left_operand = operands[i]
            right_operand = operands[i + 1]
            confidence_vs_zero = (
                (_is_confidence_attr(left_operand) and _is_zero_literal(right_operand))
                or (_is_zero_literal(left_operand) and _is_confidence_attr(right_operand))
            )
            if confidence_vs_zero:
                op_str = "==" if isinstance(op, ast.Eq) else "!="
                violations.append((node.lineno, f"claim.confidence {op_str} 0.0"))
    return violations


def test_d3_reconciler_has_no_exact_equality_against_claim_confidence() -> None:
    """D3 — core/reconciler.py uses NO `== 0.0` / `!= 0.0` against claim.confidence."""
    source = RECONCILER_PATH.read_text(encoding="utf-8")
    violations = find_exact_equality_violations(source)
    assert not violations, (
        "core/reconciler.py couples routing predicates to the ECAPA exact-0.0 "
        f"convention at lines {violations}.\n"
        "Fix: use `claim.confidence_is_no_signal` (or `not ...`) instead of "
        "`claim.confidence == 0.0` / `!= 0.0`. The exact-0.0 convention is the "
        "backend's no-signal sentinel, NOT a routing predicate — coupling to it "
        "mis-routes the common negative-cosine case (Session-119 regression)."
    )


# --- Self-tests ---

def test_d3_self_test_forward_eq_zero_detected() -> None:
    """Forward: synthetic `claim.confidence == 0.0` fires."""
    src = (
        "def rule(claim):\n"
        "    if claim.pid is None and claim.confidence == 0.0:\n"
        "        return 'x'\n"
    )
    violations = find_exact_equality_violations(src)
    assert violations, "synthetic `== 0.0` against claim.confidence should be flagged"


def test_d3_self_test_forward_neq_zero_detected() -> None:
    """Forward: synthetic `claim.confidence != 0.0` fires."""
    src = (
        "def rule(claim):\n"
        "    if claim.confidence != 0.0:\n"
        "        return 'x'\n"
    )
    violations = find_exact_equality_violations(src)
    assert violations, "synthetic `!= 0.0` against claim.confidence should be flagged"


def test_d3_self_test_forward_reversed_operand_detected() -> None:
    """Forward: reversed operand order `0.0 == claim.confidence` fires."""
    src = (
        "def rule(claim):\n"
        "    if 0.0 == claim.confidence:\n"
        "        return 'x'\n"
    )
    violations = find_exact_equality_violations(src)
    assert violations, "reversed-order `0.0 == claim.confidence` should be flagged"


def test_d3_self_test_inverse_flag_predicate_passes() -> None:
    """Inverse: flag-based predicate produces no violation."""
    src = (
        "def rule(claim):\n"
        "    if claim.pid is None and claim.confidence_is_no_signal:\n"
        "        return 'x'\n"
    )
    violations = find_exact_equality_violations(src)
    assert not violations, f"flag-based predicate should be clean, got {violations}"


def test_d3_self_test_inverse_lt_zero_threshold_passes() -> None:
    """Inverse: `claim.confidence < 0.0` (Session-119 negative-cosine catch) passes."""
    src = (
        "def rule(claim):\n"
        "    if claim.confidence_is_no_signal or claim.confidence < 0.0:\n"
        "        return 'x'\n"
    )
    violations = find_exact_equality_violations(src)
    assert not violations, f"`< 0.0` threshold should be allowed, got {violations}"


def test_d3_self_test_inverse_threshold_compare_passes() -> None:
    """Inverse: `claim.confidence < THRESHOLD` (routing threshold) passes."""
    src = (
        "def rule(claim):\n"
        "    if claim.confidence < VOICE_RECOGNITION_THRESHOLD:\n"
        "        return 'x'\n"
    )
    violations = find_exact_equality_violations(src)
    assert not violations, f"threshold comparison should be allowed, got {violations}"
