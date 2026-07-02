"""SB.8 — the persona-pack loader.

Reads + schema-validates ``persona/<persona_id>.yaml`` and returns the pack's
override dict keyed DIRECTLY at the config-global names (Lock 2 — the same
convention as ``ACTIVE_AGENTS``/``ENROLLMENT_MODE``: the profile loader merges
these into the resolved override dict and ``config._apply_profile_overrides``
writes each key verbatim via ``globals()[key] = value``).

Discipline (mirrors ``core/profile_loader.py``):
- **Pure**: reads YAML + validates. Does NOT import ``core.config`` → no
  import cycle (config's apply consumes this via the profile loader).
- **Fail-loud**: a missing pack file / missing required key / unknown key /
  malformed value crashes the boot with a message naming the file + the
  offending key + the valid set. An unknown ``persona_id`` NEVER falls back
  to companion silently (A3).
- ``yaml.safe_load`` only — untrusted-file discipline.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

from pathlib import Path

import yaml

from persona._schema import REQUIRED_KEYS, TIME_OF_DAY_KEYS

_PERSONA_DIR = Path(__file__).resolve().parent.parent / "persona"

# The persona selected when a profile declares no ``persona`` section (or a
# section without ``persona_id``) — today's product, mirroring how an absent
# ``agents:`` resolves to the full set. NOT a fallback for an UNKNOWN id —
# a declared-but-unshipped id fails loud (A3).
DEFAULT_PERSONA_ID = "companion_dog"


class PersonaError(RuntimeError):
    """Raised on any bad pack selection / file / schema violation. Fail-loud:
    a mis-configured persona pack crashes the boot with a clear message."""


def load_persona(persona_id: str) -> dict:
    """Load + validate the pack YAML; return the raw pack dict."""
    if not isinstance(persona_id, str) or not persona_id:
        raise PersonaError(
            f"persona_id must be a non-empty string; got {persona_id!r}."
        )
    path = _PERSONA_DIR / f"{persona_id}.yaml"
    if not path.is_file():
        raise PersonaError(
            f"Unknown persona_id {persona_id!r}: pack file missing at {path}. "
            f"Ship persona/{persona_id}.yaml or select a shipped pack. "
            f"(No silent fallback to {DEFAULT_PERSONA_ID!r} — a wrong persona "
            f"must fail the boot, not impersonate the default.)"
        )
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise PersonaError(f"Persona pack {path} is not valid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise PersonaError(
            f"Persona pack {path} must be a YAML mapping at top level; got "
            f"{type(raw).__name__}."
        )
    _validate(raw, persona_id, str(path))
    return raw


def _validate(raw: dict, persona_id: str, where: str) -> None:
    """Closed-set validation: every REQUIRED key present, no unknown keys,
    correct shapes. Errors name the file + key + valid set."""
    for key in raw:
        if key not in REQUIRED_KEYS:
            raise PersonaError(
                f"{where}: unknown pack key {key!r}. Valid keys: {REQUIRED_KEYS}. "
                f"(The key set is CLOSED — a non-schema key can never reach the "
                f"rendered prompt, so carrying one is always a mistake.)"
            )
    missing = [k for k in REQUIRED_KEYS if k not in raw]
    if missing:
        raise PersonaError(
            f"{where}: missing required pack key(s) {missing}. "
            f"Every pack must carry all of {REQUIRED_KEYS}."
        )
    for key in ("persona_id", "system_name_default", "voice_id",
                "persona_identity", "persona_character", "greeting_persona_line"):
        val = raw[key]
        if not isinstance(val, str) or not val.strip():
            raise PersonaError(
                f"{where}: {key} must be a non-empty string; got "
                f"{type(val).__name__} ({val!r})."
            )
    if raw["persona_id"] != persona_id:
        raise PersonaError(
            f"{where}: 'persona_id: {raw['persona_id']}' does not match the "
            f"selected persona {persona_id!r} (the file is named {persona_id}.yaml)."
        )
    fallbacks = raw["greeting_fallbacks"]
    if not isinstance(fallbacks, dict):
        raise PersonaError(
            f"{where}: greeting_fallbacks must be a mapping of "
            f"{TIME_OF_DAY_KEYS}; got {type(fallbacks).__name__}."
        )
    if set(fallbacks) != set(TIME_OF_DAY_KEYS):
        raise PersonaError(
            f"{where}: greeting_fallbacks must carry EXACTLY the keys "
            f"{TIME_OF_DAY_KEYS}; got {tuple(fallbacks)}."
        )
    for tod, templates in fallbacks.items():
        if (not isinstance(templates, list) or not templates
                or not all(isinstance(t, str) and t.strip() for t in templates)):
            raise PersonaError(
                f"{where}: greeting_fallbacks.{tod} must be a non-empty list of "
                f"non-empty strings; got {templates!r}."
            )


def resolve_persona_overrides(persona_id: str) -> dict:
    """Load the pack and key its values at the config-global names (Lock 2).

    The profile loader merges this into the resolved override dict;
    ``config._apply_profile_overrides`` writes each key verbatim. The
    companion pack's values are byte-identical to today's inline literals
    (A1 golden-gated), so the companion apply is behavior-neutral.
    """
    pack = load_persona(persona_id)
    return {
        "DEFAULT_SYSTEM_NAME": pack["system_name_default"],
        "TTS_VOICE_ID": pack["voice_id"],
        "PERSONA_IDENTITY": pack["persona_identity"],
        "PERSONA_CHARACTER": pack["persona_character"],
        "GREETING_PERSONA_LINE": pack["greeting_persona_line"],
        "GREETING_FALLBACKS": {tod: list(t) for tod, t in pack["greeting_fallbacks"].items()},
    }
