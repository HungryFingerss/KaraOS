"""SB.1 D4.2 — KaraOS instance-mode declaration guard tests.

Locks the lightweight deployment-intent mechanism landed in SB.1 D4.2:
- VALID_INSTANCE_MODES is the exhaustive {base, personal} set.
- KARAOS_INSTANCE_MODE resolves to a normalized string, env-overridable,
  default "base" (so the committed BASE config always reads "base"; Jagan's
  personal instance flips via a gitignored .env).
- pipeline.run() emits the `[Config] instance_mode=...` boot line and guards a
  typo'd env override against VALID_INSTANCE_MODES without crashing.

Heavy write-path enforcement is SB.5; this is documentation-only.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from pathlib import Path

import core.config as config

_REPO_ROOT = Path(__file__).resolve().parent.parent


def test_valid_instance_modes_is_exhaustive_base_personal():
    assert config.VALID_INSTANCE_MODES == ("base", "personal")


def test_instance_mode_resolves_to_normalized_string():
    mode = config.KARAOS_INSTANCE_MODE
    assert isinstance(mode, str)
    assert mode == mode.strip().lower()  # config normalizes via .strip().lower()
    assert mode != ""  # `... or "base"` guarantees non-empty


def test_config_default_instance_mode_is_base():
    """Source-inspection: the env-override default literal is 'base' so a fresh
    BASE checkout (env unset) declares base, independent of the runtime env the
    test happens to run under."""
    src = (_REPO_ROOT / "core" / "config.py").read_text(encoding="utf-8")
    assert 'os.getenv("KARAOS_INSTANCE_MODE", "base")' in src
    assert 'VALID_INSTANCE_MODES' in src


def test_pipeline_boot_logs_instance_mode_with_valid_guard():
    """Source-inspection: the boot declaration emits the log line, reads the config
    constant, and falls back to base on an invalid env override. P1.A1 SP-7c: the
    instance-mode check relocated from pipeline.run() to runtime/boot_checks.py::
    validate_instance_mode (engine boot-leaf home, alongside validate_tool_registries);
    run() now calls validate_instance_mode() — the substrings live in boot_checks.py."""
    src = (_REPO_ROOT / "runtime" / "boot_checks.py").read_text(encoding="utf-8")
    assert "[Config] instance_mode=" in src
    assert "config.KARAOS_INSTANCE_MODE" in src
    assert "config.VALID_INSTANCE_MODES" in src
