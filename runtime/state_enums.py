"""runtime/state_enums.py — PipelineState + CloudState enums (the pure enum pair; _set_state defers to SP-5).

Extracted VERBATIM from pipeline.py (P1.A1 SP-4 — pure leaves).
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

from enum import Enum
from enum import auto


class PipelineState(Enum):
    WATCHING     = auto()  # scanning for faces
    LISTENING    = auto()  # recording speech
    THINKING     = auto()  # LLM processing
    SPEAKING     = auto()  # TTS playing
    ENROLLING    = auto()  # enrollment flow


class CloudState(Enum):
    ONLINE  = auto()   # Together.ai working normally
    SICK    = auto()   # First failure — grace period, trying to recover
    OFFLINE = auto()   # >2 min failure — Ollama Q&A mode active
