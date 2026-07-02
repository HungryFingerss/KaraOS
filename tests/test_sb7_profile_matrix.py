"""SB.7 Step 7 (A7) + Step 8 — per-profile boot + CI matrix/coverage tripwires.

A7 extends the SB.3 registry battery (``tests/test_sb3_agent_registry.py`` T1)
into the slow.yml matrix shape (D4/D5): every profile in ``VALID_PROFILES``
resolves through the REAL loader (``profiles/<name>.yaml`` → ``ACTIVE_AGENTS``)
and boots a ``BrainOrchestrator`` that constructs EXACTLY the resolved set —
in-set agents with their registered classes, out-of-set attributes ``None``.
Rule-gated: both shipped profiles currently resolve to the full 15 (robotics
carries the ``agents: companion`` placeholder until SB.9 defines its reduced
set), so the ONLY-half is vacuous today but binds automatically the moment a
profile's set shrinks — no test edit needed.

CI wiring: the slow.yml ``perception-bench`` matrix job runs THIS file once
per profile leg with ``KARAOS_PROFILE`` set, so the env-path anchor exercises
the real env → config-apply → ``config.ACTIVE_AGENTS`` chain (not just the
loader), then the job runs ``python -m bench.perception --alert``.

Also here:
  * the SB.5-gate robustness anchor de-risking the robotics bench leg
    (``enrollment_mode="none"`` must not break ``compute_face_eer``'s
    throwaway synthetic gallery);
  * structural CI↔code drift tripwires on slow.yml — the matrix profile list
    must equal ``VALID_PROFILES`` verbatim, the legs must run the boot check
    + the D3 gate, and the slow job's pytest step must carry the Step-8
    coverage floor (``--cov`` over the 3 perception-core files +
    ``--cov-fail-under``).

Residual (flagged per the architect's Step-7 checkpoint note): the YAML can
only be verified structurally on this box — the first real matrix execution
is the nightly/dispatch run on GitHub.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import pathlib
import re

import pytest
import yaml

import core.config as config
import core.profile_loader as profile_loader
from core.brain_agent.orchestrator import _ATTR
from core.profile_loader import VALID_PROFILES, load_profile
from profiles._registry import AGENT_REGISTRY

from tests.test_sb3_agent_registry import _make_orch

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
_SLOW_YML = REPO_ROOT / ".github" / "workflows" / "slow.yml"


def _assert_boot_matches(bo, active: "frozenset[str]") -> None:
    """The A7 exact-set property, BOTH directions: every agent in ``active``
    is constructed with its registered class; every agent NOT in ``active``
    is absent (attribute is None). The negative direction is what makes this
    the matrix-shape extension of SB.3's T1 companion golden."""
    for name, spec in AGENT_REGISTRY.items():
        agent = getattr(bo, _ATTR[name])
        if name in active:
            assert agent is not None, (
                f"agent {name!r} is in the profile's ACTIVE_AGENTS but was "
                f"not constructed"
            )
            assert type(agent).__name__ == spec["class"], (
                f"{name!r} built as {type(agent).__name__}, expected "
                f"{spec['class']}"
            )
        else:
            assert agent is None, (
                f"agent {name!r} is NOT in the profile's ACTIVE_AGENTS but "
                f"was constructed — the boot loaded more than the profile's set"
            )


# ─────────────────────────────────────────────────────────────────────────────
# A7 — the matrix shape: every shipped profile, resolved via the REAL loader.
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("profile", VALID_PROFILES)
def test_a7_profile_boots_only_its_agent_set(profile, tmp_path, monkeypatch) -> None:
    resolved = load_profile(profile)
    active = resolved["ACTIVE_AGENTS"]
    bo = _make_orch(tmp_path, monkeypatch, active)
    _assert_boot_matches(bo, active)


def test_a7_reduced_set_negative_direction_is_non_vacuous(tmp_path, monkeypatch) -> None:
    """Both SHIPPED profiles currently resolve to the full 15 (robotics is the
    SB.9 placeholder), which would leave A7's ONLY-half vacuous — a guard
    never proven non-vacuous is the cousin of the bug it guards (#126/#128
    doctrine). This anchor drives the same exact-set property through a
    REDUCED synthetic set (SB.3's supermarket shape: watchdog only,
    dep-closure-safe) so the negative direction demonstrably fires TODAY,
    not only when SB.9 ships a reduced robotics set."""
    reduced = frozenset({"watchdog"})
    bo = _make_orch(tmp_path, monkeypatch, reduced)
    _assert_boot_matches(bo, reduced)


def test_a7_env_selected_profile_applied_and_boots(tmp_path, monkeypatch) -> None:
    """The env path the CI matrix legs exercise: KARAOS_PROFILE was applied at
    config-module load, so ``config.ACTIVE_AGENTS`` must equal the loader's
    resolution for that profile — then a boot constructs exactly that set.
    Locally (env unset) this runs the companion leg; in the slow.yml matrix
    each leg runs it under its own KARAOS_PROFILE."""
    name = profile_loader.KARAOS_PROFILE
    assert name in VALID_PROFILES
    resolved = load_profile(name)
    assert config.ACTIVE_AGENTS == resolved["ACTIVE_AGENTS"], (
        f"config.ACTIVE_AGENTS diverges from the loader's resolution of the "
        f"env-selected profile {name!r} — the profile apply did not land"
    )
    bo = _make_orch(tmp_path, monkeypatch, config.ACTIVE_AGENTS)
    _assert_boot_matches(bo, config.ACTIVE_AGENTS)


# ─────────────────────────────────────────────────────────────────────────────
# SB.5-gate robustness — the robotics bench leg must survive
# enrollment_mode="none" (the robotics identity mapping). compute_face_eer
# forces "persistent" for its OWN throwaway temp DB and restores the profile's
# value; result is identical because the engine recognition path is
# profile-independent.
# ─────────────────────────────────────────────────────────────────────────────
def test_a7_bench_eer_survives_non_persistent_enrollment_mode(monkeypatch) -> None:
    from bench.perception import bench

    unpatched = bench.compute_face_eer()
    monkeypatch.setattr(config, "ENROLLMENT_MODE", "none")
    gated = bench.compute_face_eer()
    assert gated == unpatched, (
        "compute_face_eer under enrollment_mode='none' diverged from the "
        "persistent-mode run — the bench-local gate override broke"
    )
    assert config.ENROLLMENT_MODE == "none", (
        "compute_face_eer leaked its enrollment-mode override — the finally "
        "restore must put back the PROFILE's value, not 'persistent'"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Structural CI↔code drift tripwires — slow.yml Step 7 matrix + Step 8 floor.
# yaml.safe_load only (untrusted-file discipline, mirrors the loader).
# ─────────────────────────────────────────────────────────────────────────────
def _slow_jobs() -> dict:
    return yaml.safe_load(_SLOW_YML.read_text(encoding="utf-8"))["jobs"]


def test_step7_ci_matrix_lists_exactly_the_valid_profiles() -> None:
    # Rule-gated cross-check: the CI matrix and VALID_PROFILES must move
    # TOGETHER — shipping a profile without a matrix leg (or vice versa)
    # fails here, never drifts silently.
    jobs = _slow_jobs()
    assert "perception-bench" in jobs, "slow.yml lost the Step-7 matrix job"
    matrix = jobs["perception-bench"]["strategy"]["matrix"]
    assert matrix["profile"] == list(VALID_PROFILES), (
        f"slow.yml matrix profiles {matrix['profile']} != shipped "
        f"VALID_PROFILES {list(VALID_PROFILES)}"
    )


def test_step7_ci_matrix_env_and_steps() -> None:
    job = _slow_jobs()["perception-bench"]
    assert job["env"]["KARAOS_PROFILE"] == "${{ matrix.profile }}", (
        "the matrix leg must select its profile via KARAOS_PROFILE"
    )
    # One profile's regression must not mask the other's result.
    assert job["strategy"]["fail-fast"] is False
    runs = [step.get("run", "") for step in job["steps"]]
    assert any("pytest tests/test_sb7_profile_matrix.py" in r for r in runs), (
        "the matrix leg must run the A7 boot check (this file)"
    )
    assert any("python -m bench.perception --alert" in r for r in runs), (
        "the matrix leg must run the D3 regression gate"
    )


def test_step8_coverage_floor_in_slow_job() -> None:
    slow_steps = _slow_jobs()["slow"]["steps"]
    pytest_step = next(
        (s for s in slow_steps if "pytest tests/" in s.get("run", "")), None)
    assert pytest_step is not None, "slow.yml lost its full-suite pytest step"
    addopts = pytest_step["env"].get("PYTEST_ADDOPTS", "")
    for target in ("--cov=core.vision", "--cov=core.voice", "--cov=core.reconciler"):
        assert target in addopts, (
            f"Step-8 coverage floor lost target {target!r} from PYTEST_ADDOPTS"
        )
    floor = re.search(r"--cov-fail-under=(\d+)", addopts)
    assert floor is not None, "Step-8 --cov-fail-under missing from PYTEST_ADDOPTS"
    assert int(floor.group(1)) >= 50, (
        "Step-8 coverage floor ratchets UPWARD only — never below the 50 "
        "landed at Step 8 (measured 57 local, minus cross-platform margin)"
    )


def test_step8_pytest_cov_pinned_in_requirements() -> None:
    req = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "pytest-cov" in req, (
        "pytest-cov missing from requirements.txt — the CI floor would die "
        "on an unrecognized --cov option"
    )
