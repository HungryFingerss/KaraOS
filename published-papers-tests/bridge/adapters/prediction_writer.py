"""Build a single prediction dict in the paper's exact JSON shape.

Schema reference: `code/benchmarking/evaluate_baseline.py:115-139`.

This is the ONLY adapter in the bridge that reads the FORBIDDEN fields
from the source row (``decision``, ``category``, ``confidence``). They
land into the ``ground_truth``, ``category``, and ``confidence`` fields
of the output dict — used downstream by the paper's metric code to
compute "correct/wrong". They are NEVER passed back to the classifier.

The strict folder split (this file separate from input_adapter.py) is
the protection — if anyone ever wires the answer back into the
classifier, the cross-file dependency is immediately visible at code
review.
"""
from __future__ import annotations

from typing import Any

# Match the paper's MAX_CONTEXT_TURNS_IN_RESULTS so loaded predictions
# are not bloated by long histories. See evaluate_baseline.py:287.
MAX_CONTEXT_TURNS_IN_RESULTS = 20


def build_prediction_row(
    sample:      dict,
    sidecar:     "dict | None",
    decision:    "str | None",
    latency:     float,
) -> dict:
    """Return one prediction dict matching the paper's shape.

    ``sidecar`` is the raw classifier output (or None on failure).
    ``decision`` is the SPEAK/SILENT/None that map_to_decision returned.
    ``latency`` is wall-clock seconds spent waiting on the classifier.
    """
    context_turns_list = sample.get("context_turns") or []
    if len(context_turns_list) > MAX_CONTEXT_TURNS_IN_RESULTS:
        context_turns_display = context_turns_list[-MAX_CONTEXT_TURNS_IN_RESULTS:]
        context_turns_total = len(context_turns_list)
    else:
        context_turns_display = context_turns_list
        context_turns_total = len(context_turns_list)

    # output_text MUST be a string per the paper's schema. Stringify
    # the sidecar dict so downstream code can parse it back if needed.
    if sidecar is None:
        output_text = "NULL"
    else:
        import json as _json_pw
        try:
            output_text = _json_pw.dumps(sidecar, separators=(",", ":"))
        except Exception:
            output_text = str(sidecar)

    return {
        "sample_id":           sample.get("decision_point_id", ""),
        # ground_truth is the paper's `decision` field — the answer.
        # ONLY the prediction-writer reads it; the classifier never sees it.
        "ground_truth":        sample.get("decision", "UNKNOWN"),
        "prediction":          decision,                            # 'SPEAK' | 'SILENT' | None
        "category":            sample.get("category", "UNKNOWN"),    # SPEAK_explicit / etc.
        "output_text":         output_text,
        "latency":             float(latency),
        "target_speaker":      sample.get("target_speaker", "N/A"),
        "all_speakers":        sample.get("all_speakers", []),
        "context_turns":       context_turns_display,
        "context_turns_total": context_turns_total,
        "current_turn":        sample.get("current_turn", {}),
        # Annotator's confidence in their LABEL — NOT the classifier's.
        "confidence":          sample.get("confidence", "N/A"),
    }


def build_payload(
    domain:        str,
    model_id:      str,
    classifier_prompt_hash: str,
    predictions:   list[dict],
    metadata:      "dict | None" = None,
) -> dict:
    """Wrap predictions in the paper's outer envelope.

    Mirrors `evaluate_baseline.py:1003-1009`'s payload shape, plus a
    `bridge_metadata` block carrying our bridge-specific context (cost,
    rows attempted, exclusions, classifier prompt hash).
    """
    payload: dict[str, Any] = {
        "dataset":                 domain,
        "model_key":               "karaos",
        "model_id":                model_id,
        "system_prompt_repeat":    1,           # we don't repeat — single classifier call
        "predictions":             list(predictions),
    }
    if metadata is not None:
        payload["bridge_metadata"] = dict(metadata)
    payload.setdefault("bridge_metadata", {})
    payload["bridge_metadata"].setdefault(
        "classifier_prompt_hash", classifier_prompt_hash
    )
    return payload
