# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors
"""SB.2.1 — profile package: the YAML profile data files + the Python override
contract (``_schema.py``). Profiles are *data* (YAML); the schema is *code*
(§8.1 ruling). Importing this package pulls in nothing from ``core`` — the
loader that consumes it stays config-free (no import cycle)."""
