"""
core/abstraction.py — Production-time text abstraction for the graph classifier.

Strips PII (names, places, system_name) from user utterances so the embedding
+ k-NN graph operates on abstract scenarios that are deployment-portable
and PII-clean.

Two-pass strategy:
  1. Registry-first — replace known persons (from `persons_in_room`) and
     `system_name` via fast regex. Microseconds. No model load.
  2. NER fallback — for any residual unknown PERSON / GPE / LOC entities,
     run spacy `en_core_web_sm`. Module-level singleton so we don't reload
     the model per call.

Times, dates, numbers, currency — NOT abstracted. They carry intent
signal (live_data_query: "What's the temperature in Mumbai right now?"
loses meaning if the time/place is stripped uniformly).

Used by:
  - `core/classifier_graph.classify_intent_graph` at production query time
  - `core/classifier_graph.handle_correction` when re-abstracting a turn
    for a new positive scenario insert
  - `bootstrap/classifier/stage_4_abstract` (offline path uses the same
    underlying spacy logic; this module is the production-time analogue)
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import re
import sys
from typing import Optional


# Module-level singleton: spacy nlp object loaded once, reused forever.
_NLP: object | None = None
_NLP_LOAD_FAILED: bool = False  # one-shot flag — don't keep retrying


def _load_spacy() -> object | None:
    """Lazy spacy loader. Returns None on failure (module not installed,
    model not downloaded). Subsequent calls short-circuit."""
    global _NLP, _NLP_LOAD_FAILED
    if _NLP is not None:
        return _NLP
    if _NLP_LOAD_FAILED:
        return None
    try:
        import spacy  # type: ignore
        _NLP = spacy.load("en_core_web_sm")
        return _NLP
    except (ImportError, OSError) as e:
        print(f"[abstraction] spacy load failed: {type(e).__name__}: {e!r} -- "
              "registry-only abstraction will be used (NER fallback disabled)")
        _NLP_LOAD_FAILED = True
        return None


# Entity types we strip via NER fallback. ORG / EVENT / PRODUCT / DATE /
# TIME / MONEY / CARDINAL / ORDINAL / PERCENT / QUANTITY all preserved.
_PERSON_NER_TYPES = frozenset({"PERSON"})
_PLACE_NER_TYPES  = frozenset({"GPE", "LOC", "FAC"})


def abstract_text(
    text: str,
    *,
    persons_in_room: "list[str] | None" = None,
    system_name: str = "Kara",
) -> "tuple[str, dict[str, str]]":
    """Abstract a string. Returns (abstracted_text, mapping).

    `mapping` is `{placeholder: original}` (e.g. `{"{P1}": "Lexi"}`) so
    callers can re-substitute names back at de-abstraction time.

    `persons_in_room` lets the registry pass deterministically replace
    known speakers in O(N) with no model load. NER pass is reserved for
    residual unknown names + places.
    """
    if not text:
        return text, {}

    persons_in_room = persons_in_room or []
    mapping: dict[str, str] = {}
    person_counter = 0
    place_counter = 0

    out = text

    # ── Pass 1: registry-first (fast, deterministic) ─────────────────────
    # Replace each known person name (case-insensitive, word-boundary) with
    # {P1}, {P2}, ... in occurrence order.
    seen_persons: dict[str, str] = {}  # lowercase name -> placeholder
    for name in persons_in_room:
        if not name or not name.strip():
            continue
        if name.lower() in seen_persons:
            continue
        person_counter += 1
        placeholder = f"{{P{person_counter}}}"
        seen_persons[name.lower()] = placeholder
        mapping[placeholder] = name
        # Word-boundary regex; case-insensitive so 'Lexi' / 'lexi' / 'LEXI' all hit
        pattern = re.compile(r"\b" + re.escape(name) + r"\b", re.IGNORECASE)
        out = pattern.sub(placeholder, out)

    # Replace system_name with {SYSTEM} (case-insensitive)
    if system_name and system_name.strip():
        sys_pattern = re.compile(r"\b" + re.escape(system_name) + r"\b", re.IGNORECASE)
        if sys_pattern.search(out):
            mapping["{SYSTEM}"] = system_name
            out = sys_pattern.sub("{SYSTEM}", out)

    # ── Pass 2: NER fallback for residual unknowns ───────────────────────
    nlp = _load_spacy()
    if nlp is None:
        return out, mapping

    # Skip NER pass if the text contains no remaining alphabetic words —
    # nothing left for NER to find.
    if not re.search(r"[A-Za-z]", out):
        return out, mapping

    try:
        doc = nlp(out)
    except Exception as e:
        print(f"[abstraction] spacy parse failed on {out!r}: {type(e).__name__}: {e!r}")
        return out, mapping

    # Collect entity spans we want to replace, sorted right-to-left so
    # earlier offsets stay valid as we mutate.
    spans: list[tuple[int, int, str]] = []
    for ent in doc.ents:
        if ent.label_ in _PERSON_NER_TYPES:
            ent_text = ent.text
            # Skip placeholders the registry pass already inserted (spacy
            # may tag {P1} as a PERSON depending on context).
            if ent_text.startswith("{") and ent_text.endswith("}"):
                continue
            # If the same surface form was already replaced, reuse the
            # placeholder for consistency.
            existing = next(
                (ph for ph, orig in mapping.items()
                 if orig.lower() == ent_text.lower() and ph.startswith("{P")),
                None,
            )
            if existing is None:
                person_counter += 1
                existing = f"{{P{person_counter}}}"
                mapping[existing] = ent_text
            spans.append((ent.start_char, ent.end_char, existing))
        elif ent.label_ in _PLACE_NER_TYPES:
            ent_text = ent.text
            if ent_text.startswith("{") and ent_text.endswith("}"):
                continue
            existing = next(
                (ph for ph, orig in mapping.items()
                 if orig.lower() == ent_text.lower() and ph.startswith("{LOC")),
                None,
            )
            if existing is None:
                place_counter += 1
                existing = f"{{LOC{place_counter}}}"
                mapping[existing] = ent_text
            spans.append((ent.start_char, ent.end_char, existing))

    if not spans:
        return out, mapping

    # Apply right-to-left to preserve indices.
    spans.sort(key=lambda s: s[0], reverse=True)
    result = out
    for start, end, placeholder in spans:
        result = result[:start] + placeholder + result[end:]
    return result, mapping


def deabstract(text: str, mapping: dict[str, str]) -> str:
    """Inverse of abstract_text. Substitutes placeholders back to original
    surface forms. Used to render `extracted_value` on classifier output
    when the matching scenario stored a {P1}/{P2} placeholder.
    """
    if not text or not mapping:
        return text
    out = text
    # Longer placeholders first so {LOC10} doesn't get clobbered by {LOC1}
    for placeholder in sorted(mapping.keys(), key=len, reverse=True):
        out = out.replace(placeholder, mapping[placeholder])
    return out
