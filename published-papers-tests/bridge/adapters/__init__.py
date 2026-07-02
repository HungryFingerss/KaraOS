"""Adapters between source samples and Kara-OS classifier I/O.

Strict folder split per BRIDGE_SPEC.md:
- input_adapter:      source row → classifier inputs (4 ALLOWED fields only)
- output_mapper:      classifier sidecar → SPEAK / SILENT decision
- prediction_writer:  prediction-shape dict matching the paper's JSON

The split exists so that "the answer" (decision/category/target_is_addressed/
addressees_in_current/reason/confidence) is read ONLY by prediction_writer
when wiring up `ground_truth` + `category` for downstream metric code.
input_adapter NEVER touches those fields. Code review red flag if it does.
"""
