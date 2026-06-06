"""runtime/text.py — Pure text / name / intent-gating helpers (NFKC, name sanitize, intent validation, yes/no).

Extracted VERBATIM from pipeline.py (P1.A1 SP-4 — pure leaves).
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import re


_NAME_EXTRACT_RE = re.compile(
    r'(?:call\s+me|calls?\s+me|my\s+name(?:\'?s)?\s+is|name(?:\'?s)?\s+is|i\'m|i\s+am|i\s+go\s+by)\s+(.+)',
    re.IGNORECASE,
)


_PHRASE_PREFIXES = re.compile(
    r"^(?:my name(?:'?s)?(?:\s+is)?|call me|i(?:'m| am)|i go by|name(?:'?s)?(?:\s+is)?|it(?:'?s)?(?:\s+is)?)\s+",
    re.IGNORECASE,
)


def sanitize_name(raw: str) -> tuple[str, str]:
    """Return (display_name, safe_id_component) from raw user-supplied input.

    Extracts the actual name from natural-language phrases like
    "People call me Jagan", "My name is Jevin", "They call me Rex".
    Searches for name-introducing patterns ANYWHERE in the string,
    not just at the start.

    display_name     — extracted name, stripped to 50 chars, used in TTS greetings.
    safe_id_component — lowercase [a-z0-9_] only, max 50 chars, used as the
                        human-readable prefix of person_id filesystem paths.
    """
    text = raw.strip()
    # Try to extract name from phrases like "People call me Jagan" anywhere in string
    m = _NAME_EXTRACT_RE.search(text)
    if m:
        extracted = m.group(1).strip(" .,!?\"'")
        # Take the first word of the extracted part (the actual name)
        first = extracted.split()[0] if extracted else ""
        extracted = first if len(first) >= 2 else extracted
    else:
        # Fallback: strip known prefixes at start, take first word
        stripped = _PHRASE_PREFIXES.sub("", text).strip(" .,!?\"'")
        first    = stripped.split()[0] if stripped else ""
        extracted = first if len(first) >= 2 else stripped
    display = (extracted if len(extracted) >= 2 else text)[:50]
    safe = re.sub(r"[^a-z0-9_-]", "_", display.lower())
    safe = re.sub(r"_+", "_", safe).strip("_")[:50]
    if not safe:
        safe = "unknown"
    return display, safe


def _user_text_gate_passes(
    user_text: "str | None",
    new_value: "str | None",
    assign_patterns: tuple,
    *,
    reject_on_empty_user_text: bool = True,
) -> bool:
    """Server-side user-text gate — shared primitive for side-effect tools.

    Session 73 (Bugs G1-G4, 2026-04-22 live run): every side-effect tool must
    verify the LLM's action matches what the user actually said. The old
    Session 71 gate used OR-logic (name appeared in turn OR assignment phrase
    present) which let "do you know the GAME called Detroit?" pass as a valid
    name assignment. This primitive enforces a stricter contract: the
    assignment phrase itself must contain the name as a capture group.

    Three usage modes:
      1. Name-verify gate (``new_value`` is str): a pattern must match AND
         its first capture group (case-insensitively) must equal new_value.
         Used for update_system_name, update_person_name, auto-confirm.
      2. Denial-signal gate (``new_value`` is None): any pattern match
         suffices — no name-capture verification. Used for
         report_identity_mismatch where the gate just needs a clear denial.
      3. Empty user_text path: default REJECT (``reject_on_empty_user_text
         = True``). Mutation tools firing via KAIROS proactive prompts have
         no user utterance to verify against — the LLM is acting unilaterally,
         which is the exact risk class these gates exist to block.

    The existing shutdown handler has its own hand-rolled gate and is NOT
    migrated to this primitive.
    """
    import re as _re
    _lt = _nfkc_lower(user_text).strip()
    if not _lt:
        return not reject_on_empty_user_text
    _nv_lower = _nfkc_lower(new_value).strip() if new_value is not None else None
    for pat in assign_patterns:
        m = _re.search(pat, _lt, _re.IGNORECASE)
        if not m:
            continue
        if new_value is None:
            # Denial-signal gate — match alone is sufficient.
            return True
        if not m.groups():
            continue
        _captured = _nfkc_lower(m.group(1)).strip()
        # Exact match — the captured single-word name equals the proposal.
        if _captured == _nv_lower:
            return True
        # P0.3 fix (multi-word contiguous substring): (\w+) captures only the
        # first word — "call me Sarah Jane" → capture="sarah", proposal=
        # "sarah jane". Accept iff proposal STARTS with the captured word AND
        # the FULL proposal appears as a contiguous substring of user_text.
        # Contiguous check prevents the LLM from combining words from different
        # parts of the utterance ("call me sarah … is jane" ≠ "Sarah Jane").
        # NFKC applied above defeats homoglyph spoofing on all three inputs.
        if _captured and _nv_lower.startswith(_captured):
            if _nv_lower in _lt:
                return True
    return False


def _nfkc_lower(s: "str | None") -> str:
    """NFKC-normalized casefold — defeats Unicode homoglyph spoofing.

    Threat model (per architect review): the classifier may extract "Kаra"
    (Cyrillic а, U+0430) when the user actually said "Kara" (Latin a).
    Without normalization the grounding check would compare two different
    code points as if they were the same — a classic spoofing surface.
    NFKC collapses compatibility variants; casefold handles case-insensitive
    comparison more robustly than lower() for Unicode.

    P0.S5 refactor (2026-05-20): NFKC step delegates to
    :func:`core.sanitize._nfkc_only` so there is a single source of truth
    for NFKC normalization across the grounding-gate (this site) and the
    LLM-input wrap (:func:`core.sanitize.wrap_user_input`). Casefold stays
    here — only the grounding-gate use case wants case-insensitive
    comparison; LLM input preserves case via the sibling helper."""
    from core.sanitize import _nfkc_only
    return _nfkc_only(s or "").casefold()


def _strip_im_contraction(s: "str | None") -> str:
    """Session 94 Fix #2: strip leading ``Im`` / ``I'm`` / ``I\u2019m`` contraction.

    Whisper occasionally compresses ``I'm <Name>`` into ``Im<Name>`` (no
    space, no apostrophe) — observed in the 2026-04-22 live canary where
    "I'm Lexi" became "Imlexi" in the STT. Whisper also loses the capital
    on the following letter in the compression (so "Imlexi" has lowercase
    'l', not uppercase 'L'). When this lands in either the classifier's
    ``extracted_value`` or the LLM's ``tool_args[arg_key]``, grounding
    fails spuriously ("Imlexi" isn't a substring of "I'm Lexi", even
    though semantically they're the same name).

    Requires the INITIAL letter to be capital ``I`` (distinguishes the
    first-person pronoun start from mid-sentence words). Accepts either
    case for the letter after ``m``, since Whisper's compression
    occasionally drops the name's capital. False positive: "Important" at
    the start of an extracted_value/tool_arg would strip to "portant" —
    acceptable trade-off because those inputs should be names, not common
    words. Returns input unchanged when no match or input empty."""
    if not s:
        return s or ""
    import re as _re
    m = _re.match(r"^I['\u2019]?m([a-zA-Z].*)$", s)
    return m.group(1) if m else s


def _intent_allows(
    tool_name: str,
    turn_intent: str,
    confidence: float,
    extracted_value: "str | None",
    user_text: str,
    tool_args: dict,
) -> tuple[bool, str]:
    """P1.4 server-side validator consuming the shadow classifier's sidecar.

    Four rules, checked in order (short-circuit on first failure):
      1. Tool pass-through — not in TOOL_INTENT_MAP → (True, "tool not gated")
      2. Intent match — classifier's turn_intent must equal the tool's required
      3. Confidence floor — shutdown uses INTENT_SHUTDOWN_CONF_MIN (0.80),
         all others use INTENT_CONFIDENCE_MIN (0.75)
      4. Grounding + arg cross-check — when extracted_value is non-empty:
         - NFKC-casefolded extracted_value must be a substring of NFKC-casefolded
           user_text (defeats homoglyph spoofing + case/whitespace variance)
         - When the tool has arg_key, NFKC-casefolded tool_args[arg_key] must
           equal NFKC-casefolded extracted_value (catches the LLM fabricating
           a rename-target that differs from what the user actually said)

    Returns (allowed, reason). reason is a short diagnostic for the [Intent]
    log line. Session 80 observation: the dual gate (intent + confidence) is
    robust to both classifier failure modes seen in live data — wrong-label-
    low-conf (Turn 19) and conservative-label-high-conf (Turn 23). This
    validator relies on that robustness.

    Shadow mode: callers MUST continue using the regex gate for dispatch
    decisions until INTENT_FALLBACK_TO_REGEX flips to False at P1.17. The
    validator's verdict is logged side-by-side with the regex verdict so
    divergences are observable and the calibration corpus keeps growing."""
    from core.config import (
        TOOL_INTENT_MAP, INTENT_CONFIDENCE_MIN, INTENT_SHUTDOWN_CONF_MIN,
    )
    required, arg_key = TOOL_INTENT_MAP.get(tool_name, (None, None))
    if required is None:
        return (True, "tool not gated")
    if turn_intent != required:
        return (False, f"intent={turn_intent} expected={required}")
    min_conf = (
        INTENT_SHUTDOWN_CONF_MIN if tool_name == "shutdown"
        else INTENT_CONFIDENCE_MIN
    )
    if confidence < min_conf:
        return (False, f"confidence {confidence:.2f} < {min_conf}")
    if extracted_value:
        # Session 94 Fix #2: strip Whisper's "Im"/"I'm" contraction prefix
        # before grounding check. "Imlexi" vs user_text "I'm Lexi" (clean
        # STT) would fail substring match without this; after stripping
        # both sides to "Lexi", grounding succeeds as intended.
        _ev_stripped = _strip_im_contraction(extracted_value)
        _ev = _nfkc_lower(_ev_stripped)
        _ut = _nfkc_lower(user_text)
        if _ev not in _ut:
            return (False, "extracted_value not grounded in user_text")
        if arg_key:
            _arg_raw = tool_args.get(arg_key, "")
            # Apply the same contraction-strip to tool_args so the
            # cross-check treats "Lexi" and "Imlexi" as equivalent when
            # one came from a clean STT and the other from a mangled one.
            _arg_stripped = _strip_im_contraction(_arg_raw)
            _arg = _nfkc_lower(_arg_stripped)
            if _arg != _ev:
                return (
                    False,
                    f"tool arg {_arg_raw!r} != user said {extracted_value!r}",
                )
    elif arg_key and tool_args.get(arg_key):
        # Session 87 grounding-gap fix: the Session 86 live run had a case
        # where the classifier honestly abstained (extracted_value=None,
        # intent=assign_own_name, conf=0.80) but the LLM still proposed a
        # ``{"name": "Kara"}`` arg hallucinated from history. The original
        # code's ``if extracted_value:`` block skipped all grounding when
        # the classifier said "I see the intent but can't extract a value",
        # so the hallucinated arg slipped through and renamed the person to
        # Kara. This elif catches the case: if the classifier didn't
        # extract but the LLM proposed an arg, the arg itself must appear
        # in user_text. Closes the silent-hallucination path that
        # accumulated one false rename in just 10 divergence rows of
        # production observation — would have grown into a pattern.
        # Session 94: also strip Im-contraction from the proposed arg.
        _proposed = tool_args[arg_key]
        _proposed_stripped = _strip_im_contraction(_proposed)
        if _nfkc_lower(_proposed_stripped) not in _nfkc_lower(user_text):
            return (
                False,
                f"tool arg {_proposed!r} not grounded (classifier extracted no value)",
            )
    # P0.S10 D3 — Identity-denial structural gate for report_identity_mismatch.
    # The tool has arg_key=None (only arg is free-text `reason`), so neither
    # extracted_value grounding nor arg_key cross-check fires above. This
    # adds the missing third gate: user_text MUST contain an identity-claim-
    # rejection phrase. Canary 2026-05-27 dual-gate failed because the brain
    # fired this tool on "I don't have any job" (topic-denial, NOT identity-
    # denial). LLM judgment + classifier judgment both wrong; this structural
    # gate is the safety net. Patterns matched case-insensitively against
    # NFKC-casefolded user_text (Plan v4 §2.2 6-pattern set, path A).
    if tool_name == "report_identity_mismatch":
        import re  # noqa: PLC0415 — local import; pattern matching is hot-path
        from core.config import IDENTITY_DENIAL_PATTERNS  # noqa: PLC0415
        _ut = _nfkc_lower(user_text)
        if not any(re.search(p, _ut, re.IGNORECASE) for p in IDENTITY_DENIAL_PATTERNS):
            return (
                False,
                "report_identity_mismatch requires explicit identity-rejection "
                "phrase in user_text (P0.S10 D3 — topic-denial does not warrant "
                "identity-mismatch tool firing)",
            )
    return (True, "intent match")


def _detect_yes_no(text: str) -> str:
    """Returns 'yes', 'no', or 'unclear' from a short spoken response."""
    t = text.lower()
    if any(w in t for w in ("yes", "yeah", "yep", "yup", "sure", "absolutely",
                             "of course", "definitely", "correct", "right", "true",
                             "i am", "that's me", "thats me")):
        return "yes"
    if any(w in t for w in ("no", "nope", "nah", "never", "not", "negative", "i'm not")):
        return "no"
    return "unclear"
