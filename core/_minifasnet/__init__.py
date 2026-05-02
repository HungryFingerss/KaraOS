"""Vendored MiniFASNet anti-spoofing model.

Source: https://github.com/minivision-ai/Silent-Face-Anti-Spoofing (MIT License, Copyright (c) 2020 Minivision).
Only the model architecture (model.py) is vendored here; all other project code is original.
Pretrained weights ship separately under models/antispoof_weights/ (also MIT).

Scope: 2-class / 3-class face liveness classifier on 80x80 BGR crops. Used by
core/vision.py:AntiSpoofChecker to gate greetings and recognition_update gallery writes.
"""
from .model import MiniFASNetV2, MiniFASNetV1SE, load_pretrained

__all__ = ["MiniFASNetV2", "MiniFASNetV1SE", "load_pretrained"]
