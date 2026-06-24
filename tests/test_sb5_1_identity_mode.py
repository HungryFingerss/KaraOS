"""SB.5 §5 Step-1 — identity / retention-mode test battery.

Two-axis identity model (enrollment_mode × retention_mode) wired ACTIVE at
config-load time, mirroring the SB.3 agents / SB.4.1 blocks axes. Gated by:
- IA  golden equivalence — apply(companion) == persistent/durable (== today,
  byte-neutral; T1 companion golden stays GREEN), apply(robotics) ==
  none/ephemeral (SB.5 Q1 public-service-robot mapping),
- IC  the 9-cell coherence validator (FORALL 9 → 4 clean-accept / 2 session_only
  -deferred-reject-with-message / 3 incoherent-named-pair-reject; Finding 1),
- IR  Reading B (Q2) — an ABSENT identity SECTION → config base defaults (not
  keyed); an absent KEY *within* a declared section → fail-closed transient/
  ephemeral via the FAILCLOSED_* defaults,
- IS  schema fail-loud — identity unknown-key / bad enrollment enum / bad
  retention enum each ProfileError via _validate,
- ID  deletion-proof — VALID_RETENTION_MODES gone, `retention` not in SCHEMA,
  `identity` present with both keys wired to the new tuples,
- IT  tuple-order is LOAD-BEARING (longest-lived → shortest-lived; the rank
  derivation depends on it).

Plan: karaos-org-discussions/solidify-base/SB5-1-plan-v2.md §5 Step-1.
Ratified findings: SB5-1-step1-pass3-findings.md (Q1 + Q2 + Finding 3).
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import pytest

import core.config as config
import profiles._schema as schema
from core.config import _apply_profile_overrides
from core.profile_loader import (
    ProfileError,
    _resolve,
    _validate,
    _validate_identity_coherence,
    load_profile,
)
from profiles._schema import (
    FAILCLOSED_ENROLLMENT_MODE,
    FAILCLOSED_RETENTION_LIFETIME,
    SCHEMA,
    VALID_ENROLLMENT_MODES,
    VALID_RETENTION_LIFETIMES,
)


# ────────────────────────────────────────────────────────────────────────────
# The 9-cell FORALL contract (Finding 1 — authoritative v2 §6 split, NOT v1 §5).
# 4 clean-accept / 2 session_only-deferred-reject / 3 incoherent-named-pair-reject.
# ────────────────────────────────────────────────────────────────────────────
_CLEAN_ACCEPT = [
    ("persistent", "durable"),
    ("persistent", "ephemeral"),
    ("transient", "ephemeral"),
    ("none", "ephemeral"),
]
_SESSION_ONLY_REJECT = [
    ("persistent", "session_only"),
    ("transient", "session_only"),
]
_INCOHERENT_REJECT = [
    ("transient", "durable"),
    ("none", "durable"),
    ("none", "session_only"),  # incoherent fires FIRST (r_rank>e_rank), not session_only
]
_ALL_NINE = _CLEAN_ACCEPT + _SESSION_ONLY_REJECT + _INCOHERENT_REJECT


def test_forall_9_is_exactly_partitioned() -> None:
    """The 9 (enrollment × retention) cells partition into 4 / 2 / 3 — no cell
    is double-counted, none missing. Guards the Finding-1 split from drift."""
    assert len(_ALL_NINE) == len(VALID_ENROLLMENT_MODES) * len(VALID_RETENTION_LIFETIMES) == 9
    assert len(_ALL_NINE) == len(set(_ALL_NINE)), "a cell is double-counted"
    grid = {(e, r) for e in VALID_ENROLLMENT_MODES for r in VALID_RETENTION_LIFETIMES}
    assert set(_ALL_NINE) == grid, "the 9 enumerated cells must cover the full grid"
    assert (len(_CLEAN_ACCEPT), len(_SESSION_ONLY_REJECT), len(_INCOHERENT_REJECT)) == (4, 2, 3)


# ────────────────────────────────────────────────────────────────────────────
# IC — coherence validator (direct unit, FORALL 9)
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("enrollment,retention", _CLEAN_ACCEPT)
def test_ic_clean_accept_does_not_raise(enrollment: str, retention: str) -> None:
    """The 4 coherent non-session_only cells validate silently (return None)."""
    assert _validate_identity_coherence(enrollment, retention, "identity") is None


@pytest.mark.parametrize("enrollment,retention", _SESSION_ONLY_REJECT)
def test_ic_session_only_deferred_reject_with_message(enrollment: str, retention: str) -> None:
    """The 2 coherent-rank session_only cells fail LOUD with the deferred-cycle
    message — NOT the incoherent-named-pair message."""
    with pytest.raises(ProfileError) as exc:
        _validate_identity_coherence(enrollment, retention, "identity")
    msg = str(exc.value)
    assert "session_only enforcement lands in a later cycle" in msg
    assert "incoherent identity" not in msg


@pytest.mark.parametrize("enrollment,retention", _INCOHERENT_REJECT)
def test_ic_incoherent_named_pair_reject(enrollment: str, retention: str) -> None:
    """The 3 incoherent cells (retention outlives enrollment) fail LOUD naming
    BOTH modes. none/session_only lands HERE (incoherent check fires first),
    NOT in the session_only-deferred bucket."""
    with pytest.raises(ProfileError) as exc:
        _validate_identity_coherence(enrollment, retention, "identity")
    msg = str(exc.value)
    assert "incoherent identity" in msg
    assert "outlives" in msg
    assert enrollment in msg and retention in msg
    assert "session_only enforcement lands in a later cycle" not in msg


# ────────────────────────────────────────────────────────────────────────────
# IC (integration) — coherence runs through the live _resolve identity branch
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("enrollment,retention", _CLEAN_ACCEPT)
def test_ic_resolve_keys_overrides_on_clean_accept(enrollment: str, retention: str) -> None:
    """_resolve's identity branch keys ENROLLMENT_MODE/RETENTION_MODE directly
    (Lock-2) for every clean-accept cell."""
    out = _resolve({"profile": "companion", "identity": {
        "enrollment_mode": enrollment, "retention_mode": retention}})
    assert out["ENROLLMENT_MODE"] == enrollment
    assert out["RETENTION_MODE"] == retention


@pytest.mark.parametrize("enrollment,retention", _SESSION_ONLY_REJECT + _INCOHERENT_REJECT)
def test_ic_resolve_raises_on_reject(enrollment: str, retention: str) -> None:
    """_resolve fail-louds (does NOT silently downgrade) on every reject cell."""
    with pytest.raises(ProfileError):
        _resolve({"profile": "companion", "identity": {
            "enrollment_mode": enrollment, "retention_mode": retention}})


# ────────────────────────────────────────────────────────────────────────────
# IR — Reading B (Q2): absent SECTION vs absent KEY-within-section
# ────────────────────────────────────────────────────────────────────────────

def test_ir_absent_section_not_keyed_resolves_to_base_default() -> None:
    """Reading B — a profile with NO identity section does NOT key ENROLLMENT_MODE/
    RETENTION_MODE at all (resolves to the config base defaults persistent/durable
    = today), mirroring the absent agents:/blocks: → base-set precedent."""
    out = _resolve({"profile": "companion"})
    assert "ENROLLMENT_MODE" not in out
    assert "RETENTION_MODE" not in out


def test_ir_absent_keys_within_declared_section_fail_closed() -> None:
    """Reading B — absent KEYS inside a DECLARED identity section fall to the
    fail-closed FAILCLOSED_* defaults (transient/ephemeral), a coherent cell."""
    out = _resolve({"profile": "companion", "identity": {}})
    assert out["ENROLLMENT_MODE"] == FAILCLOSED_ENROLLMENT_MODE == "transient"
    assert out["RETENTION_MODE"] == FAILCLOSED_RETENTION_LIFETIME == "ephemeral"


def test_ir_one_absent_key_uses_failclosed_for_the_missing_axis_only() -> None:
    """A declared section with only enrollment_mode → retention falls to the
    fail-closed default; the declared axis is honored verbatim."""
    out = _resolve({"profile": "companion", "identity": {"enrollment_mode": "persistent"}})
    assert out["ENROLLMENT_MODE"] == "persistent"
    assert out["RETENTION_MODE"] == FAILCLOSED_RETENTION_LIFETIME == "ephemeral"


# ────────────────────────────────────────────────────────────────────────────
# IA — golden equivalence (companion byte-neutral == today; robotics Q1 mapping)
# ────────────────────────────────────────────────────────────────────────────

def test_ia_companion_applies_persistent_durable_byte_neutral() -> None:
    """apply(companion) == persistent/durable — explicit == today's base defaults,
    so T1's companion byte-neutral golden stays GREEN."""
    g: dict = {}
    _apply_profile_overrides(g, load_profile("companion"))
    assert g["ENROLLMENT_MODE"] == "persistent"
    assert g["RETENTION_MODE"] == "durable"


def test_ia_robotics_applies_none_ephemeral_q1_mapping() -> None:
    """apply(robotics) == none/ephemeral — the SB.5 Q1 public-service-robot
    mapping (no personal PII on a shared robot by default)."""
    g: dict = {}
    _apply_profile_overrides(g, load_profile("robotics"))
    assert g["ENROLLMENT_MODE"] == "none"
    assert g["RETENTION_MODE"] == "ephemeral"


def test_ia_config_base_defaults_match_companion_today() -> None:
    """The config base-default globals are persistent/durable — the same values
    companion declares, so the live (companion) boot is byte-neutral whether the
    apply keys them or the absent-section path falls through to the base."""
    assert config.ENROLLMENT_MODE == "persistent"
    assert config.RETENTION_MODE == "durable"


# ────────────────────────────────────────────────────────────────────────────
# IS — schema fail-loud (T5-style)
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("case", ["unknown_key", "bad_enrollment_enum", "bad_retention_enum"])
def test_is_identity_schema_fail_loud(case: str) -> None:
    """Malformed identity input fail-louds with ProfileError at _validate time
    (structural — distinct from the coherence validator which runs at _resolve)."""
    if case == "unknown_key":
        bad = {"profile": "companion", "identity": {"not_a_key": "x"}}
    elif case == "bad_enrollment_enum":
        bad = {"profile": "companion", "identity": {"enrollment_mode": "banana"}}
    else:  # bad_retention_enum
        bad = {"profile": "companion", "identity": {"retention_mode": "forever"}}
    with pytest.raises(ProfileError):
        _validate(bad, "companion", "<sb5>")


def test_is_well_formed_identity_passes_validate() -> None:
    """A well-formed identity section clears _validate (the schema gate is shape-
    only; coherence is _resolve's job)."""
    _validate(
        {"profile": "companion", "identity": {
            "enrollment_mode": "persistent", "retention_mode": "durable"}},
        "companion", "<sb5>",
    )


# ────────────────────────────────────────────────────────────────────────────
# ID — deletion-proof + IT — tuple-order load-bearing
# ────────────────────────────────────────────────────────────────────────────

def test_id_valid_retention_modes_constant_deleted() -> None:
    """The pre-SB.5 VALID_RETENTION_MODES constant is GONE from _schema (renamed
    to the two identity-axis tuples)."""
    assert not hasattr(schema, "VALID_RETENTION_MODES")


def test_id_retention_section_renamed_to_identity_in_schema() -> None:
    """The old `retention` SCHEMA section is GONE; `identity` is the active section
    carrying both axis keys wired to the new tuples."""
    assert "retention" not in SCHEMA
    assert "identity" in SCHEMA
    ident = SCHEMA["identity"]
    assert ident["kind"] == "section"
    keys = ident["keys"]
    assert set(keys) == {"enrollment_mode", "retention_mode"}
    assert keys["enrollment_mode"]["enum"] is VALID_ENROLLMENT_MODES
    assert keys["retention_mode"]["enum"] is VALID_RETENTION_LIFETIMES


def test_it_tuple_order_is_load_bearing_longest_to_shortest() -> None:
    """Tuple ORDER drives the rank derivation (rank = len - index). Reordering
    silently breaks the 9-cell semantics — pin it longest-lived → shortest-lived."""
    assert VALID_ENROLLMENT_MODES == ("persistent", "transient", "none")
    assert VALID_RETENTION_LIFETIMES == ("durable", "session_only", "ephemeral")
    # rank sanity: index 0 is the longest-lived (highest rank).
    e_rank = {v: len(VALID_ENROLLMENT_MODES) - VALID_ENROLLMENT_MODES.index(v)
              for v in VALID_ENROLLMENT_MODES}
    r_rank = {v: len(VALID_RETENTION_LIFETIMES) - VALID_RETENTION_LIFETIMES.index(v)
              for v in VALID_RETENTION_LIFETIMES}
    assert e_rank == {"persistent": 3, "transient": 2, "none": 1}
    assert r_rank == {"durable": 3, "session_only": 2, "ephemeral": 1}
