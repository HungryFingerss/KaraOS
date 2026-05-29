"""
P0.2 — prior_person_type fail-closed default (structural AST invariant).

Every read of `prior_person_type` that supplies a fallback default must use
"stranger" (or an equivalent fail-closed value). Using "known" or "best_friend"
as a fallback silently grants privileges to sessions where the field is absent,
which is a privilege-escalation bug (Session 70 Bug Q class).

Violation shapes detected:
  .get("prior_person_type", "known")         ← .get with bad default
  .get("prior_person_type") or "known"       ← or-fallback with bad default
  .setdefault("prior_person_type", ...)      ← setdefault with bad value
  .setdefault("prior_person_type", None)     ← setdefault with None (leaks via get)

Legitimate shapes allowed:
  .get("prior_person_type", "stranger")
  .get("prior_person_type", "stranger") or fallback
  .setdefault("prior_person_type", "stranger")
  .setdefault("prior_person_type", X.get("person_type", "stranger"))
  .pop("prior_person_type", None)            ← removal, not a read
  session["prior_person_type"] = value       ← write, not a read with default

DOES NOT IMPORT pipeline. Reads pipeline.py and core/*.py as raw text and
ast.parse()s them. Avoids all Windows torchaudio DLL side-effects.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

import ast
import re
from pathlib import Path

import pytest

# ── paths ──────────────────────────────────────────────────────────────────────

_ROOT = Path(__file__).resolve().parent.parent
PIPELINE_PATH = _ROOT / "pipeline.py"

# core/*.py excluding config.py (config holds the constant definitions, not
# the violation-prone read sites)
_CORE_PATHS = [
    p for p in (_ROOT / "core").glob("*.py")
    if p.name != "config.py"
]

# Test files intentionally contain violation strings as fixture literals.
# They must never be scanned.
_SCAN_PATHS = [PIPELINE_PATH] + _CORE_PATHS

# ── constants ──────────────────────────────────────────────────────────────────

FIELD = "prior_person_type"

# These default values escalate privilege when prior_person_type is absent.
BAD_DEFAULTS = frozenset({"known", "best_friend"})

# None is also bad as a setdefault value: if session has no prior_person_type
# key, setdefault("prior_person_type", None) WRITES None; subsequent
# .get("prior_person_type", "stranger") returns None (the field now EXISTS),
# so the fail-closed default is bypassed.
BAD_SETDEFAULT_VALUES = BAD_DEFAULTS | frozenset({None})


# ── AST helpers ───────────────────────────────────────────────────────────────

def _annotate_parents(tree: ast.AST) -> None:
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            child.parent = node  # type: ignore[attr-defined]


def _enclosing_function(node: ast.AST) -> str:
    parent = getattr(node, "parent", None)
    while parent is not None:
        if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return parent.name
        parent = getattr(parent, "parent", None)
    return "<module>"


# ── violation detectors ───────────────────────────────────────────────────────

def _bad_get_default(node: ast.AST) -> str | None:
    """
    X.get("prior_person_type", "known")
    Returns the bad default string, or None if not a violation.
    """
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    if not (isinstance(func, ast.Attribute) and func.attr == "get"):
        return None
    if len(node.args) < 2:
        return None
    key_arg = node.args[0]
    if not (isinstance(key_arg, ast.Constant) and key_arg.value == FIELD):
        return None
    default_arg = node.args[1]
    if isinstance(default_arg, ast.Constant) and default_arg.value in BAD_DEFAULTS:
        return repr(default_arg.value)
    return None


def _bad_or_fallback(node: ast.AST) -> str | None:
    """
    X.get("prior_person_type") or "known"
    BoolOp(Or, [Call(.get(...)), Constant("known")])
    """
    if not isinstance(node, ast.BoolOp):
        return None
    if not isinstance(node.op, ast.Or):
        return None
    if len(node.values) < 2:
        return None
    left = node.values[0]
    right = node.values[-1]
    # Left must be a .get("prior_person_type") call (no default arg)
    if not isinstance(left, ast.Call):
        return None
    func = left.func
    if not (isinstance(func, ast.Attribute) and func.attr == "get"):
        return None
    if not left.args:
        return None
    key_arg = left.args[0]
    if not (isinstance(key_arg, ast.Constant) and key_arg.value == FIELD):
        return None
    # Right must be a bad constant
    if isinstance(right, ast.Constant) and right.value in BAD_DEFAULTS:
        return repr(right.value)
    return None


def _bad_setdefault(node: ast.AST) -> str | None:
    """
    X.setdefault("prior_person_type", "known")
    X.setdefault("prior_person_type", None)
    X.setdefault("prior_person_type", X.get("person_type", "known"))
    """
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    if not (isinstance(func, ast.Attribute) and func.attr == "setdefault"):
        return None
    if len(node.args) < 2:
        return None
    key_arg = node.args[0]
    if not (isinstance(key_arg, ast.Constant) and key_arg.value == FIELD):
        return None
    val_arg = node.args[1]

    # Direct bad constant (including None)
    if isinstance(val_arg, ast.Constant):
        if val_arg.value in BAD_SETDEFAULT_VALUES:
            return repr(val_arg.value)
        return None

    # X.get("person_type", "known") as the value expression
    if isinstance(val_arg, ast.Call):
        inner_func = val_arg.func
        if isinstance(inner_func, ast.Attribute) and inner_func.attr == "get":
            if len(val_arg.args) >= 2:
                inner_default = val_arg.args[1]
                if isinstance(inner_default, ast.Constant) and inner_default.value in BAD_DEFAULTS:
                    return f"get(..., {inner_default.value!r})"
    return None


# ── scanner ───────────────────────────────────────────────────────────────────

def _scan_source(source: str, filename: str = "<string>") -> list[str]:
    """Return human-readable violation strings. Empty = no violations."""
    tree = ast.parse(source, filename=filename)
    _annotate_parents(tree)

    failures: list[str] = []

    for node in ast.walk(tree):
        violation: str | None = None
        shape: str = ""

        if (v := _bad_get_default(node)) is not None:
            violation, shape = v, ".get(field, bad)"
        elif (v := _bad_or_fallback(node)) is not None:
            violation, shape = v, ".get(field) or bad"
        elif (v := _bad_setdefault(node)) is not None:
            violation, shape = v, ".setdefault(field, bad)"
        else:
            continue

        line = getattr(node, "lineno", "?")
        fn = _enclosing_function(node)
        failures.append(
            f"  {filename}:{line} (in {fn}): {shape} — bad default {violation}"
        )

    return failures


# ── main invariant test ───────────────────────────────────────────────────────

def test_no_bad_prior_person_type_defaults_in_production_code():
    """
    Whole-file scan of pipeline.py + core/*.py (excl. config.py).
    Any read of prior_person_type with a non-fail-closed default is a
    privilege-escalation bug.
    """
    all_failures: list[str] = []
    for path in _SCAN_PATHS:
        source = path.read_text(encoding="utf-8")
        failures = _scan_source(source, filename=str(path.name))
        all_failures.extend(failures)

    assert not all_failures, (
        f"prior_person_type reads with escalating defaults found "
        f"(allowed default: 'stranger' only):\n"
        + "\n".join(all_failures)
        + "\n\nFix: replace every bad default with 'stranger' (fail-closed)."
    )


# ── violation shape self-tests ────────────────────────────────────────────────

@pytest.mark.parametrize("violation_src", [
    # 1. .get with "known" default
    """
def watchdog(sess):
    t = sess.get("prior_person_type", "known")
""",
    # 2. .get with "best_friend" default
    """
def watchdog(sess):
    t = sess.get("prior_person_type", "best_friend")
""",
    # 3. or-fallback with "known"
    """
def handler(sess):
    t = sess.get("prior_person_type") or "known"
""",
    # 4. or-fallback with "best_friend"
    """
def handler(sess):
    t = sess.get("prior_person_type") or "best_friend"
""",
    # 5. setdefault with "known"
    """
def handler(sess):
    sess.setdefault("prior_person_type", "known")
""",
    # 6. setdefault with None (bypasses fail-closed via later .get)
    """
def handler(sess):
    sess.setdefault("prior_person_type", None)
""",
    # 7. setdefault where the value expression is .get("person_type", "known")
    """
def handler(sess):
    sess.setdefault("prior_person_type", sess.get("person_type", "known"))
""",
    # 8. setdefault with "best_friend"
    """
def handler(sess):
    sess.setdefault("prior_person_type", "best_friend")
""",
    # 9. Nested inside a closure, no enclosing function in allowlist
    """
def conversation_turn(person_id):
    def _inner(session):
        v = session.get("prior_person_type", "known")
    _inner(_active_sessions[person_id])
""",
])
def test_detector_catches_all_violation_shapes(violation_src):
    """Each synthetic violation MUST trigger at least one detector."""
    failures = _scan_source(violation_src)
    assert len(failures) >= 1, (
        f"Detector missed a violation shape:\n{violation_src}"
    )


# ── legitimate shape self-tests ───────────────────────────────────────────────

@pytest.mark.parametrize("legitimate_src", [
    # 1. Fail-closed .get default
    """
def handler(sess):
    t = sess.get("prior_person_type", "stranger")
""",
    # 2. or-fallback with "stranger"
    """
def handler(sess):
    t = sess.get("prior_person_type") or "stranger"
""",
    # 3. setdefault with "stranger"
    """
def handler(sess):
    sess.setdefault("prior_person_type", "stranger")
""",
    # 4. setdefault where value comes from .get("person_type", "stranger")
    """
def handler(sess):
    sess.setdefault("prior_person_type", sess.get("person_type", "stranger"))
""",
    # 5. pop — removal, not a privilege-granting read
    """
def handler(sess):
    sess.pop("prior_person_type", None)
""",
    # 6. Direct write — not a read with fallback
    """
def handler(sess, val):
    sess["prior_person_type"] = val
""",
    # 7. .get without any default — no fallback supplied, no violation
    """
def handler(sess):
    t = sess.get("prior_person_type")
""",
    # 8. Reading a DIFFERENT field — should not trigger
    """
def handler(sess):
    t = sess.get("person_type", "known")
""",
    # 9. setdefault on a different field
    """
def handler(sess):
    sess.setdefault("person_type", "known")
""",
    # 10. or-fallback on a different field
    """
def handler(sess):
    t = sess.get("person_type") or "known"
""",
])
def test_detector_allows_legitimate_patterns(legitimate_src):
    """Each synthetic legitimate pattern MUST NOT trigger a false positive."""
    failures = _scan_source(legitimate_src)
    assert failures == [], (
        f"False positive on legitimate pattern:\n{legitimate_src}\n"
        f"Failures: {failures}"
    )
