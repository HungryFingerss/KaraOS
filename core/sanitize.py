"""Input sanitization for LLM-call boundaries (P0.S5).

Single source of truth for prompt-injection hardening. Every agent that
constructs ``messages=[{"role": "user", "content": ...}]`` MUST route the
content through :func:`wrap_user_input` — structurally enforced by
``tests/test_p0_s5_wrap_user_input_coverage.py``.

INJECTION DEFENSE clause distribution policy (Plan v1 §1.P3 locked option
(c) — documentation-only): the wrap itself is the structural protection.
The model's prose-injection resistance ("Ignore previous instructions...",
Cyrillic homoglyph) is the model's own responsibility per P0.S3 §3.7
precedent — semantic-spoofing is NOT a P0.S5 concern. P0.S5 closes the
STRUCTURAL injection vectors (closing the ``<user_said>`` tag, embedding
``<system>`` tags, Bidi-override character spoofing).

Tag adjudication: ``<user_said>`` (NOT ``<user_text>``) per the existing
``INJECTION DEFENSE`` clause at ``core/brain.py:910-942`` and the
``_classify_intent`` precedent at ``core/brain.py:1068``.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import re
import unicodedata


# Threat-class characters: U+202E Right-to-Left Override (canonical Bidi
# attack — can reorder displayed text in operator's terminal to hide
# injection), U+200B-U+200D (zero-width spaces — invisible text splitters),
# plus other Bidi control characters per Unicode Annex #9.
_REJECTED_CONTROL_CHARS: frozenset[str] = frozenset({
    "\u202e",  # RTL Override (canonical Bidi attack vector)
    "\u202d",  # LTR Override
    "\u200e",  # LTR Mark
    "\u200f",  # RTL Mark
    "\u200b",  # Zero-width space
    "\u200c",  # ZWNJ
    "\u200d",  # ZWJ
    "\u2066",  # LRI
    "\u2067",  # RLI
    "\u2068",  # FSI
    "\u2069",  # PDI
})


# XML tag injection: strip standalone tags that look like system-prompt
# control structures. NOT a general HTML strip — narrowed to known threat
# shapes plus ``user_said`` (defends against self-close injection where a
# malicious user types ``</user_said>...<user_said>``).
_XML_TAG_INJECTION_RE = re.compile(
    r"</?(?:system|assistant|user|tool|function_call|im_start|im_end|user_said)[^>]*>",
    re.IGNORECASE,
)


def _nfkc_only(s: str) -> str:
    """NFKC normalization without casefold.

    Companion to :func:`pipeline._nfkc_lower` which lowercases for the
    grounding-gate use case (Session 80 P1.4). LLM input must preserve
    case for semantic meaning, so this sibling omits casefold.
    """
    return unicodedata.normalize("NFKC", s or "")


def wrap_user_input(text: str) -> str:
    """Sanitize and wrap raw user text for LLM consumption.

    Pipeline:

      1. Reject control-character injection — ``\\u202e`` and siblings
         raise :class:`ValueError` (fail-loud per P0.S3 precedent).
      2. NFKC-normalize to defeat compatibility-variant spoofing.
      3. Strip XML-tag injection (``<system>``, ``</user>``, etc.) AND
         ``<user_said>``-self-close injection.
      4. Wrap in ``<user_said>...</user_said>`` tags (canonical tag per
         ``core/brain.py:910-942`` INJECTION DEFENSE clause; matches
         existing ``_classify_intent`` precedent at ``core/brain.py:1068``).

    Returns the wrapped string. Caller passes the return value as the
    ``messages[]`` content for any ``{"role": "user", ...}`` entry.

    Raises :class:`ValueError` on control-character injection.
    Programmer-error / threat-input discipline matching P0.S3/P0.S4 —
    fail-loud at boundary so the operator can grep the traceback for the
    offending source and downstream broad-except wrappers
    (``_poll_once`` + ``_emotion_process_background`` per P0.S4 §3.3)
    convert it into a logged + continued state without pipeline crash.

    Byte-identical contract for clean ASCII input (Plan v1 §1.P4): for
    a string containing no control chars, no XML-tag-injection shapes,
    and no NFKC-non-canonical codepoints, ``wrap_user_input(s)`` returns
    ``f"<user_said>{s}</user_said>"`` byte-for-byte. This locks the
    classifier-refactor invariant: pre-P0.S5 and post-P0.S5 produce
    identical ``user_msg`` strings for clean input → classifier accuracy
    on the golden set must not drift.
    """
    if text is None:
        text = ""
    # Step 1: control-character rejection
    for c in text:
        if c in _REJECTED_CONTROL_CHARS:
            raise ValueError(
                f"wrap_user_input: control character {c!r} (U+{ord(c):04X}) "
                f"detected in user input. Rejected per P0.S5 prompt-injection "
                f"hardening — U+202E and siblings are Bidi-attack vectors that "
                f"can reorder displayed text. If this is a legitimate use case, "
                f"file P0.S5.X scope expansion."
            )
    # Step 2: NFKC normalize
    text = _nfkc_only(text)
    # Step 3: strip XML-tag injection (including user_said self-close)
    text = _XML_TAG_INJECTION_RE.sub("", text)
    # Step 4: wrap with canonical tag
    return f"<user_said>{text}</user_said>"
