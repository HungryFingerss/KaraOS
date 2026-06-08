# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors
"""P1.A1 SP-7a — boot-time tool-registry consistency validation (extracted from
pipeline.run()). Engine-generic: validates that the supplied tool registries are
internally consistent with the brain's TOOLS list; raises RuntimeError on any
mismatch. The companion passes its own registries (brain.TOOLS, _TOOL_FALLBACKS,
_TOOL_HANDLERS) as params; a different profile reuses this with its registries.
"""

from __future__ import annotations

import core.config as config
from core.config import TOOL_PRIVILEGES


def validate_tool_registries(_BRAIN_TOOLS, _TOOL_FALLBACKS, _TOOL_HANDLERS):
    """Validate brain.TOOLS is consistent with the privilege / intent / fallback /
    handler registries. Raises RuntimeError on mismatch; returns None.

    ORDERING NOTE: the env-before-tool-registry ordering the comments below describe
    is enforced at the run() call site (validate_required_env() runs first).
    """
    _tool_names = {t["function"]["name"] for t in _BRAIN_TOOLS}
    _missing = _tool_names - set(TOOL_PRIVILEGES)
    if not (not _missing):
        raise RuntimeError(f'TOOL_PRIVILEGES missing entries for: {sorted(_missing)}. Every tool in brain.TOOLS must have a privilege row in core/config.py — add them before launch.')

    # ── Intent-gate registry integrity check (P0.S6 D2) ───────────────────────
    # ORDERING INVARIANT: this assertion MUST run AFTER the TOOL_PRIVILEGES
    # check above. Privilege misconfiguration is the more common shape (missing
    # row in TOOL_PRIVILEGES blocks ALL callers); surfacing it first gives the
    # operator the right error. Intent-gate misconfiguration is the secondary
    # check (a tool in TOOLS without a TOOL_INTENT_MAP entry would slip past
    # classifier gating but still dispatch privilege-correctly).
    #
    # ORDERING vs P0.S3: this assertion runs AFTER validate_required_env() so
    # env-var errors surface first (P0.S3 ordering anchor).
    #
    # Spec: tests/p0_s6_intent_gates_plan_v1.md §1.D2 (ordering convention
    # locked at the call site so future maintainers grepping "ORDERING
    # INVARIANT" find all three invariants — P0.S2 dashboard, P0.S3 env, P0.S6
    # intent-gate — at the surface they affect).
    _intent_known = set(config.TOOL_INTENT_MAP) | set(config.INTENT_OPTIONAL_TOOLS)
    _intent_missing = _tool_names - _intent_known
    _intent_orphans = _intent_known - _tool_names
    if not (not _intent_missing):
        raise RuntimeError(f'Tools missing from TOOL_INTENT_MAP ∪ INTENT_OPTIONAL_TOOLS: {sorted(_intent_missing)}. Add to TOOL_INTENT_MAP if it needs classifier-gate verification, OR to INTENT_OPTIONAL_TOOLS if intentionally exempt (see core/config.py rationale block).')
    if not (not _intent_orphans):
        raise RuntimeError(f'Tools in intent registry but not in brain.TOOLS: {sorted(_intent_orphans)}. Remove the registry entry OR re-add to brain.TOOLS.')

    # ── Fallback registry integrity check (P0.S6 D3) ──────────────────────────
    # ORDERING INVARIANT: this assertion MUST run AFTER the intent-gate check
    # above. Intent-gate misconfiguration is the security-relevant shape;
    # fallback-registry misconfiguration is a UX shape (silent turn when the
    # LLM emits zero content alongside a tool call) — surface security errors
    # first.
    #
    # Spec: tests/p0_s6_intent_gates_plan_v1.md §1.D3 (registry covers every
    # tool with a non-empty stripped fallback string; the comment block at
    # pipeline.py:375 warns that "Every tool MUST have a non-empty fallback
    # to prevent silent turns" — this assertion enforces it structurally).
    _fb_missing = _tool_names - set(_TOOL_FALLBACKS)
    _fb_orphans = set(_TOOL_FALLBACKS) - _tool_names
    _fb_degenerate = {k for k, v in _TOOL_FALLBACKS.items() if not v.strip()}
    if not (not _fb_missing):
        raise RuntimeError(f'_TOOL_FALLBACKS missing entries for: {sorted(_fb_missing)}. Every tool in brain.TOOLS must have a fallback string in pipeline.py:376 to prevent silent turns when the LLM emits zero content alongside the tool call.')
    if not (not _fb_orphans):
        raise RuntimeError(f'_TOOL_FALLBACKS has entries for tools not in brain.TOOLS: {sorted(_fb_orphans)}. Remove the registry entry OR re-add to brain.TOOLS.')
    if not (not _fb_degenerate):
        raise RuntimeError(f'_TOOL_FALLBACKS has empty/whitespace-only fallback strings for: {sorted(_fb_degenerate)}. Fallbacks MUST be non-empty after str.strip() to actually surface a spoken response.')

    # ── Handler registry integrity check (P0.S6 D4) ───────────────────────────
    # ORDERING INVARIANT: this assertion MUST run AFTER the fallback check
    # above. Handler-registry misconfiguration is the most operationally
    # visible shape (a tool the LLM calls would hit `handler = None` and
    # short-circuit the dispatch); fallback-registry checks fail-loud earlier.
    #
    # Spec: tests/p0_s6_intent_gates_plan_v1.md §1.D4 (introduced at Plan v1
    # Pass-2 grep when architect surfaced _TOOL_HANDLERS as the 4th tool
    # registry; INLINE_DISPATCHED_TOOLS is the companion set covering tools
    # consumed via inline ask_stream callbacks instead of _execute_tool
    # dispatch).
    _handler_known = set(_TOOL_HANDLERS) | set(config.INLINE_DISPATCHED_TOOLS)
    _handler_missing = _tool_names - _handler_known
    _handler_orphans = set(_TOOL_HANDLERS) - _tool_names
    if not (not _handler_missing):
        raise RuntimeError(f'Tools missing from _TOOL_HANDLERS ∪ INLINE_DISPATCHED_TOOLS: {sorted(_handler_missing)}. Add to _TOOL_HANDLERS if dispatched through _execute_tool, OR to INLINE_DISPATCHED_TOOLS if consumed via inline ask_stream callbacks (see core/config.py rationale block).')
    if not (not _handler_orphans):
        raise RuntimeError(f'_TOOL_HANDLERS has entries for tools not in brain.TOOLS: {sorted(_handler_orphans)}. Remove the handler entry OR re-add to brain.TOOLS.')


def validate_instance_mode() -> None:
    """SB.1 D4.2 — KaraOS instance-mode boot declaration. Documents deployment
    intent (base = cloneable/publishable; personal = Jagan's local instance).
    Lightweight: log only. Write-path enforcement lands in SB.5. Flags a typo'd
    env override (not in VALID_INSTANCE_MODES) without crashing — SB.1 is
    documentation-only. P1.A1 SP-7c: lifted verbatim from pipeline.run() to the
    engine boot-check home (alongside validate_tool_registries).
    """
    _instance_mode = config.KARAOS_INSTANCE_MODE
    if _instance_mode not in config.VALID_INSTANCE_MODES:
        print(
            f"[Config] WARNING — KARAOS_INSTANCE_MODE={_instance_mode!r} is not one of "
            f"{config.VALID_INSTANCE_MODES}; treating as 'base'. (SB.1 D4.2)"
        )
        _instance_mode = "base"
    print(f"[Config] instance_mode={_instance_mode}")
