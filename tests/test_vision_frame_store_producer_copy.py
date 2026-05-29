"""P0.6.7v2 — VisionFrameStore producer-copy invariant (AST source-inspection).

The frame is a mutable numpy ndarray.  cv2.VideoCapture.read() may return a
buffer that is overwritten on the next .read() — meaning a stored reference
would race against the next camera frame.

Every producer that calls `_vision_frame_store.set_frame(...)` MUST pass a
COPIED ndarray as the first positional arg.  This test scans pipeline.py via
AST, finds every call to `set_frame` on a VisionFrameStore attribute, and
asserts the first arg expression contains a `.copy()` method call.

The set_frame() method itself can't enforce this at runtime — `.flags.owndata`
is True for both numpy.copy() output AND for freshly-allocated arrays from
cv2.VideoCapture (depending on cv2 internals).  Source-inspection at the call
site is the only reliable guard.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import ast
import pathlib

PIPELINE_PATH = pathlib.Path(__file__).parent.parent / "pipeline.py"


def _contains_copy_call(node: ast.AST) -> bool:
    """True if the AST subtree contains a `.copy()` method call."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
            if sub.func.attr == "copy":
                return True
    return False


def _is_set_frame_call(call: ast.Call) -> bool:
    """True if call shape is `*._vision_frame_store.set_frame(...)`.

    Matches:
      _vision_frame_store.set_frame(...)
      pipeline._vision_frame_store.set_frame(...)
      self._vision_frame_store.set_frame(...)
      anything.set_frame(...) where the receiver attr ends in 'vision_frame_store'
    """
    if not isinstance(call.func, ast.Attribute):
        return False
    if call.func.attr != "set_frame":
        return False
    # Receiver is call.func.value — verify it is an Attribute or Name
    # ending in `_vision_frame_store`.
    receiver = call.func.value
    if isinstance(receiver, ast.Name):
        return receiver.id.endswith("_vision_frame_store")
    if isinstance(receiver, ast.Attribute):
        return receiver.attr.endswith("_vision_frame_store")
    return False


def _collect_set_frame_calls(tree: ast.AST) -> list[ast.Call]:
    return [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _is_set_frame_call(node)
    ]


class TestProducerCopyInvariant:
    def test_pipeline_has_at_least_one_set_frame_call(self) -> None:
        """Sanity guard: if pipeline.py drops all set_frame call sites
        accidentally (e.g. during a refactor), the test corpus becomes
        empty and the .copy() assertions trivially pass.  Anchor a
        positive count here."""
        src = PIPELINE_PATH.read_text(encoding="utf-8")
        tree = ast.parse(src)
        calls = _collect_set_frame_calls(tree)
        assert len(calls) >= 1, (
            "pipeline.py contains zero calls to _vision_frame_store.set_frame(). "
            "Either the producer was removed (regression) or the call shape "
            "changed in a way the AST detector doesn't recognize."
        )

    def test_every_set_frame_call_passes_a_copy(self) -> None:
        """For every call to set_frame(frame_expr, ts), the first positional
        arg expression must contain a `.copy()` method call."""
        src = PIPELINE_PATH.read_text(encoding="utf-8")
        tree = ast.parse(src)
        calls = _collect_set_frame_calls(tree)

        violations: list[str] = []
        for call in calls:
            if not call.args:
                violations.append(
                    f"  L{call.lineno}: set_frame() called with no positional args"
                )
                continue
            first_arg = call.args[0]
            if not _contains_copy_call(first_arg):
                # ast.unparse for the diagnostic message — Python 3.9+
                try:
                    expr_src = ast.unparse(first_arg)
                except Exception:
                    expr_src = "<unparseable>"
                violations.append(
                    f"  L{call.lineno}: set_frame({expr_src}, ...) — "
                    "first arg has no .copy() call"
                )

        assert not violations, (
            "VisionFrameStore producer-copy invariant violated.\n"
            "Every set_frame(frame, ts) call MUST pass a copied ndarray "
            "(e.g. frame.copy()) to avoid racing consumers against the next "
            "camera buffer.\n\n"
            "Violations:\n" + "\n".join(violations)
        )
