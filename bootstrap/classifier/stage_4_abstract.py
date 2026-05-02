"""Stage 4 -- Strip PII via spacy NER.

PERSON entities -> {P1}, {P2}, ... (per-utterance, first-occurrence indexing)
GPE / LOC      -> {LOC1}, {LOC2}, ...
Times, dates, numbers, currency -- NOT replaced (preserve intent signal).

Also rewrites the classifier's `extracted_value` so it points at the
placeholder when the original value was a person name (keeps the
abstraction internally consistent).

Usage from CLI:
  python -m bootstrap.classifier.stage_4_abstract

The `abstract_text()` helper is also exported for reuse from tests.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

CACHE_DIR = Path(__file__).parent / "cache"
INPUT_PATH = CACHE_DIR / "classified_samples.jsonl"
OUTPUT_PATH = CACHE_DIR / "abstracted_samples.jsonl"

SPACY_MODEL = "en_core_web_sm"

_nlp = None  # lazy global so import doesn't pull spacy until needed


def _load_spacy():
    """Lazy spacy loader. Returns None if spacy isn't installed -- tests
    can monkeypatch around this with a fake `_apply_ner` instead."""
    global _nlp
    if _nlp is not None:
        return _nlp
    try:
        import spacy  # type: ignore
    except ImportError:
        print("[stage_4_abstract] spacy not installed -- pip install spacy && "
              f"python -m spacy download {SPACY_MODEL}")
        return None
    try:
        _nlp = spacy.load(SPACY_MODEL)
    except OSError:
        print(f"[stage_4_abstract] spacy model {SPACY_MODEL} not found -- run: "
              f"python -m spacy download {SPACY_MODEL}")
        return None
    return _nlp


# Entity types we abstract:
PERSON_TYPES = frozenset({"PERSON"})
PLACE_TYPES  = frozenset({"GPE", "LOC", "FAC"})
# Things we deliberately do NOT abstract: DATE, TIME, MONEY, CARDINAL, ORDINAL,
# QUANTITY, PERCENT, EVENT, ORG, LANGUAGE, etc. -- they carry intent signal.


def _replace_entities_with_spacy(text: str, nlp) -> tuple[str, dict[str, str]]:
    """Run spacy NER + abstract PERSON/PLACE entities into placeholders.

    Returns (abstracted_text, mapping). Mapping is {original_text: placeholder}
    so callers can rewrite related fields (extracted_value) consistently.
    """
    doc = nlp(text)
    mapping: dict[str, str] = {}
    person_counter = 0
    place_counter = 0
    spans: list[tuple[int, int, str]] = []

    for ent in doc.ents:
        if ent.label_ in PERSON_TYPES:
            key = ent.text
            if key not in mapping:
                person_counter += 1
                mapping[key] = f"{{P{person_counter}}}"
        elif ent.label_ in PLACE_TYPES:
            key = ent.text
            if key not in mapping:
                place_counter += 1
                mapping[key] = f"{{LOC{place_counter}}}"
        else:
            continue
        spans.append((ent.start_char, ent.end_char, mapping[ent.text]))

    if not spans:
        return text, mapping

    # Apply replacements right-to-left so earlier offsets stay valid.
    spans.sort(key=lambda s: s[0], reverse=True)
    out = text
    for start, end, placeholder in spans:
        out = out[:start] + placeholder + out[end:]
    return out, mapping


def abstract_text(text: str, nlp=None) -> tuple[str, dict[str, str]]:
    """Public: abstract a string; returns (abstracted, mapping).

    If nlp is None, attempts to load spacy lazily. If spacy is unavailable,
    returns (text, {}) -- caller decides whether that's acceptable.
    """
    if nlp is None:
        nlp = _load_spacy()
    if nlp is None:
        return text, {}
    return _replace_entities_with_spacy(text, nlp)


def _rewrite_extracted_value(value: "str | None", mapping: dict[str, str]) -> "str | None":
    """If extracted_value matches an entity that got abstracted, swap it
    for the placeholder. Otherwise return as-is. None passes through."""
    if value is None or not value:
        return value
    if value in mapping:
        return mapping[value]
    # Try case-insensitive / whitespace-tolerant match
    norm = value.strip()
    for orig, placeholder in mapping.items():
        if orig.strip().lower() == norm.lower():
            return placeholder
    return value


def main() -> int:
    if not INPUT_PATH.exists():
        print(f"[stage_4_abstract] missing {INPUT_PATH}; run stage_3_classify first")
        return 2

    nlp = _load_spacy()
    if nlp is None:
        return 2

    written = 0
    skipped = 0
    with INPUT_PATH.open("r", encoding="utf-8") as in_fh, \
         OUTPUT_PATH.open("w", encoding="utf-8") as out_fh:
        for line_num, line in enumerate(in_fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"  [skip] line {line_num}: invalid JSON: {e!r}")
                skipped += 1
                continue
            try:
                abstracted, mapping = _replace_entities_with_spacy(rec["raw_text"], nlp)
            except Exception as e:
                print(f"  [skip] line {line_num}: spacy error: {e!r}")
                skipped += 1
                continue
            out_rec = {
                "abstract_text":    abstracted,
                "intent_label":     rec.get("intent_label"),
                "extracted_value":  _rewrite_extracted_value(rec.get("extracted_value"), mapping),
                "confidence":       float(rec.get("confidence", 0.0)),
                "source_tag":       rec.get("source_tag", "unknown"),
                "source_version":   rec.get("source_version", "unknown"),
                "source_ref":       rec.get("source_ref"),
                "model_id":         rec.get("model_id"),
                "abstract_rule_version": 1,
            }
            out_fh.write(json.dumps(out_rec) + "\n")
            written += 1
            if line_num % 200 == 0:
                out_fh.flush()
                print(f"  [{line_num}] written={written} skipped={skipped}")

    print(f"[stage_4_abstract] done -- wrote {written}, skipped {skipped} -> {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
