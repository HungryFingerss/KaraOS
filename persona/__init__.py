# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors
"""SB.8 — persona packs (PURE DATA + schema; D2).

One data-only YAML per persona at ``persona/<persona_id>.yaml``, validated by
``persona/_schema.py`` and loaded by ``core/persona_loader.py`` (selected by
the profile's ``persona.persona_id`` at apply-at-load). No code in packs —
zero supply-chain surface, mirroring ``profiles/``.
"""
