"""SB.2.1 — the profile loader.

Reads ``KARAOS_PROFILE``, loads + schema-validates the selected profile YAML,
resolves the ``llm.provider`` shorthand into the 4 per-role leaves, and returns
the override dict. The dict is applied onto ``core/config.py``'s globals by
``config._apply_profile_overrides`` at the END of config-module load (so both
``config.X`` and ``from core.config import X`` consumers bind the profiled value).

Discipline:
- **Pure**: reads YAML + validates + resolves. Does NOT import ``core.config``
  and does NOT mutate anything → no import cycle (config imports THIS at its end,
  never vice versa). T8 enforces the no-config-import structurally.
- **Fail-loud** (mirrors the ``KARAOS_INSTANCE_MODE`` typo-guard + the SP-7c
  ``validate_instance_mode`` pattern): a user-editable profile must crash the
  boot with a clear message naming the file + the offending key/value + the
  valid set, never silently mis-configure.
- ``yaml.safe_load`` only (never ``load``) — untrusted-file discipline.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import os
from pathlib import Path

import yaml

from profiles._schema import (
    SCHEMA,
    LLM_ROLES,
    LLM_LEAF_KEYS,
    PROVIDER_BUNDLES,
    VALID_PROVIDERS,
    CLOUD_TIMING_MAP,
)
from profiles._registry import AGENT_REGISTRY, AGENT_BUNDLES  # SB.3 agent-membership axis

# Env-selected deployment SHAPE. Default "companion" (today). Composed with the
# orthogonal KARAOS_INSTANCE_MODE retention axis (which stays in config.py).
KARAOS_PROFILE: str = os.getenv("KARAOS_PROFILE", "companion").strip().lower() or "companion"

# Shipped profiles. SB.2.2 adds "supermarket"; selecting an unshipped name
# fail-louds (T5). robotics is the engine-shared placeholder.
VALID_PROFILES: tuple[str, ...] = ("companion", "robotics")

_PROFILES_DIR = Path(__file__).resolve().parent.parent / "profiles"


class ProfileError(RuntimeError):
    """Raised on any bad profile selection / file / schema violation. Fail-loud:
    a mis-configured profile crashes the boot with a clear message."""


def load_profile(profile_name: "str | None" = None) -> dict:
    """Load + validate + resolve a profile. Returns the override dict consumed by
    ``config._apply_profile_overrides``. ``profile_name`` defaults to the
    env-selected ``KARAOS_PROFILE`` (the production path); tests pass an explicit
    name."""
    name = (profile_name if profile_name is not None else KARAOS_PROFILE)
    if name not in VALID_PROFILES:
        raise ProfileError(
            f"Unknown/unimplemented KARAOS_PROFILE={name!r}. "
            f"Valid profiles: {VALID_PROFILES}. "
            f"(Set the KARAOS_PROFILE env var to a shipped profile, or ship the "
            f"profile in SB.2.2+.)"
        )
    path = _PROFILES_DIR / f"{name}.yaml"
    if not path.is_file():
        raise ProfileError(
            f"Profile file missing: {path}. Every entry in VALID_PROFILES must "
            f"have a profiles/<name>.yaml. (Profile {name!r} is registered but "
            f"its YAML is absent.)"
        )
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ProfileError(f"Profile {path} is not valid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise ProfileError(
            f"Profile {path} must be a YAML mapping at top level; got "
            f"{type(raw).__name__}."
        )
    _validate(raw, name, str(path))
    return _resolve(raw)


def _validate(raw: dict, profile_name: str, where: str) -> None:
    """Validate ``raw`` against SCHEMA. Fail-loud on: unknown section / unknown
    key / bad type / bad enum / malformed leaf. Errors name the file + the
    offending key/value + the valid set."""
    for section in raw:
        if section not in SCHEMA:
            raise ProfileError(
                f"{where}: unknown top-level section {section!r}. "
                f"Valid sections: {tuple(SCHEMA)}."
            )

    # profile sentinel — if declared, must be a str matching the selected name.
    if "profile" in raw:
        decl = raw["profile"]
        if not isinstance(decl, str):
            raise ProfileError(
                f"{where}: 'profile' must be a string; got {type(decl).__name__}."
            )
        if decl != profile_name:
            raise ProfileError(
                f"{where}: 'profile: {decl}' does not match the selected profile "
                f"{profile_name!r} (the file is named {profile_name}.yaml)."
            )

    for section, body in raw.items():
        if section == "profile":
            continue
        spec = SCHEMA[section]
        if spec.get("kind") == "scalar":
            _check_scalar(section, body, spec, where)
            continue
        if spec.get("kind") == "agent_select":
            _check_agent_select(section, body, where)
            continue
        # section
        if not isinstance(body, dict):
            raise ProfileError(
                f"{where}: section {section!r} must be a mapping; got "
                f"{type(body).__name__}."
            )
        keyspec = spec["keys"]
        for key, val in body.items():
            if key not in keyspec:
                raise ProfileError(
                    f"{where}: unknown key {section}.{key!r}. "
                    f"Valid keys in {section!r}: {tuple(keyspec)}."
                )
            sub = keyspec[key]
            kind = sub.get("kind")
            if kind == "leaf":
                _check_leaf(section, key, val, where)
            elif kind == "cloud_timing":
                _check_cloud_timing(section, key, val, where)
            else:
                _check_scalar(f"{section}.{key}", val, sub, where)


def _check_scalar(name: str, val, spec: dict, where: str) -> None:
    expected = spec["type"]
    # bool is a subclass of int — guard against True/False sneaking into int
    # fields and vice versa. Our scalar fields are only str/bool, so an exact
    # type match is correct and strict.
    if type(val) is not expected:
        raise ProfileError(
            f"{where}: {name} must be {expected.__name__}; got "
            f"{type(val).__name__} ({val!r})."
        )
    if "enum" in spec and val not in spec["enum"]:
        raise ProfileError(
            f"{where}: {name}={val!r} is not one of {tuple(spec['enum'])}."
        )


def _check_leaf(section: str, role: str, val, where: str) -> None:
    if not isinstance(val, dict):
        raise ProfileError(
            f"{where}: {section}.{role} must be a mapping of "
            f"{LLM_LEAF_KEYS}; got {type(val).__name__}."
        )
    for k, v in val.items():
        if k not in LLM_LEAF_KEYS:
            raise ProfileError(
                f"{where}: unknown LLM leaf key {section}.{role}.{k!r}. "
                f"Valid: {LLM_LEAF_KEYS}."
            )
        if not isinstance(v, str):
            raise ProfileError(
                f"{where}: {section}.{role}.{k} must be a string (a model name / "
                f"base_url / env-var NAME); got {type(v).__name__}. "
                f"(Secrets never live in the YAML — api_key_env is the env var NAME.)"
            )


def _check_cloud_timing(section: str, key: str, val, where: str) -> None:
    if not isinstance(val, dict):
        raise ProfileError(
            f"{where}: {section}.{key} must be a mapping of {tuple(CLOUD_TIMING_MAP)}; "
            f"got {type(val).__name__}."
        )
    for k, v in val.items():
        if k not in CLOUD_TIMING_MAP:
            raise ProfileError(
                f"{where}: unknown cloud-timing key {section}.{key}.{k!r}. "
                f"Valid: {tuple(CLOUD_TIMING_MAP)}."
            )
        if type(v) is not int:  # bool is an int subclass — reject True/False
            raise ProfileError(
                f"{where}: {section}.{key}.{k} must be an int (seconds); got "
                f"{type(v).__name__} ({v!r})."
            )


def _check_agent_select(section: str, val, where: str) -> None:
    """SB.3 — `agents:` is a bundle-shorthand string (∈ AGENT_BUNDLES) OR a
    list[str] of AGENT_REGISTRY keys. Fail-loud on unknown bundle / unknown
    agent name / wrong type (mirrors the LLM-provider enum)."""
    if isinstance(val, str):
        if val not in AGENT_BUNDLES:
            raise ProfileError(
                f"{where}: agents={val!r} is not a known agent bundle. "
                f"Valid bundles: {tuple(AGENT_BUNDLES)}."
            )
    elif isinstance(val, list):
        for name in val:
            if not isinstance(name, str):
                raise ProfileError(
                    f"{where}: agents list entries must be agent-name strings; "
                    f"got {type(name).__name__} ({name!r})."
                )
            if name not in AGENT_REGISTRY:
                raise ProfileError(
                    f"{where}: agents entry {name!r} is not a registered agent. "
                    f"Valid: {tuple(AGENT_REGISTRY)}."
                )
    else:
        raise ProfileError(
            f"{where}: agents must be a bundle-name string or a list of agent "
            f"names; got {type(val).__name__} ({val!r})."
        )


def _validate_dep_closure(active: "frozenset[str]") -> None:
    """SB.3 §6.1 (D4 dep-closure) — every active agent's INTER-agent deps must
    also be active. An inter-agent dep is a dep tag that is itself a registry key
    (only ``embed`` today). A profile with `schema` but not `embed` fails LOUD at
    load — never crashes the topo-build. Moot for companion (all registered)."""
    for name in active:
        for dep in AGENT_REGISTRY[name]["deps"]:
            if dep in AGENT_REGISTRY and dep not in active:
                raise ProfileError(
                    f"agent {name!r} requires inter-agent dep {dep!r}, which is "
                    f"not in the active set {sorted(active)}. Register {dep!r} or "
                    f"drop {name!r}."
                )


def _resolve(raw: dict) -> dict:
    """Expand the ``llm.provider`` shorthand into the 4 per-role leaves; explicit
    per-role overrides win. Pass persona/hardware/retention through unchanged
    (declared-only hooks in SB.2.1 — config's apply ignores them). Returns the
    override dict."""
    out: dict = {}
    llm_raw = raw.get("llm", {})

    leaves: dict = {}
    provider = llm_raw.get("provider")
    if provider is not None:
        if provider not in PROVIDER_BUNDLES:
            # Defensive — _validate already enum-checks; this guarantees there is
            # NO silent fall-back to cloud when a bundle is missing (T6 RED).
            raise ProfileError(
                f"llm.provider={provider!r} has no bundle in PROVIDER_BUNDLES "
                f"({VALID_PROVIDERS}). Refusing to silently fall back to cloud."
            )
        for role in LLM_ROLES:
            leaves[role] = dict(PROVIDER_BUNDLES[provider][role])

    # Explicit per-role overrides win over the bundle (per-field merge).
    for role in LLM_ROLES:
        override = llm_raw.get(role)
        if isinstance(override, dict):
            leaves.setdefault(role, {}).update(override)

    out_llm: dict = {role: leaves[role] for role in LLM_ROLES if role in leaves}
    if "cloud" in llm_raw:
        out_llm["cloud"] = dict(llm_raw["cloud"])
    if out_llm:
        out["llm"] = out_llm

    if "features" in raw:
        out["features"] = dict(raw["features"])

    # Declared-only hooks — passed through for completeness; apply ignores them.
    for sect in ("persona", "hardware", "retention"):
        if sect in raw:
            out[sect] = dict(raw[sect])

    # SB.3 — agent-membership axis → ACTIVE_AGENTS (Lock 2: keyed directly, NOT
    # `agents`, so the apply's globals()[key]=value writes config.ACTIVE_AGENTS).
    # YAML section is `agents:`; absent → full set (un-profiled / companion).
    agents_raw = raw.get("agents")
    if agents_raw is None:
        active = frozenset(AGENT_REGISTRY)
    elif isinstance(agents_raw, str):
        active = frozenset(AGENT_BUNDLES[agents_raw])
    else:
        active = frozenset(agents_raw)
    _validate_dep_closure(active)
    out["ACTIVE_AGENTS"] = active

    return out
