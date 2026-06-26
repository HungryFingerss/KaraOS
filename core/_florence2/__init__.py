"""Vendored Florence-2 object-detection model.

Source: https://huggingface.co/microsoft/Florence-2-large (MIT License, Copyright (c) Microsoft Corporation),
pinned at upstream commit 21a599d414c4d928c9032694c424fb94458e3594. Only the modeling code is vendored here:
configuration_florence2.py + modeling_florence2.py + processing_florence2.py, committed byte-identical.

License signals (Resolution C — mirrors core/_minifasnet/, ratified SB.6 2026-06-25):
  - Repo level: MIT (Microsoft) — see core/_florence2/LICENSE.
  - File level: the three .py carry HuggingFace's transformers-template Apache-2.0 header (preserved
    byte-identical; modifying a vendored license header is itself a defect). This directory is therefore
    EXCLUDED from tools/add_spdx_headers.py — our sweep stamps OUR authorship on OUR code; vendored
    third-party code keeps its own license and stays out of the sweep, period, whether MIT or Apache.

Pretrained weights download via from_pretrained into the HuggingFace cache (structurally uncommittable).
Loaded directly via this vendored module — NOT trust_remote_code against the hub — so the modeling code is
under review and the supply-chain is pinned to the recorded SHA.

Scope: Florence-2 vision-language model for object detection / region grounding on KaraOS frames. Used by
core/object_detection.py (SB.6 Step 2).
"""
from .configuration_florence2 import Florence2Config
from .modeling_florence2 import Florence2ForConditionalGeneration
from .processing_florence2 import Florence2Processor

__all__ = ["Florence2Config", "Florence2ForConditionalGeneration", "Florence2Processor"]
