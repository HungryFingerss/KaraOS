"""SB.2.1 — profile-mechanism test battery (T1–T8).

Behavior-neutral profile loader + schema + apply-at-config-load wiring. Gated by:
- T1 golden snapshot (companion == today, env-tainted keys excluded via a
  transitive taint closure over config.py's AST — PI-A; never compares a secret),
- T2 derived-constant-consistency on a synthetic provider-flip + the PI-C strip,
- T3 no-late-mutation, T4 no-config-bypassing-reader (P0.S6 scope),
- T5 schema fail-loud, T6 robotics loads + no-silent-cloud-fallback,
- T7 features.* → real config flag, T8 loader has no core.config import.

Plan: karaos-org-discussions/solidify-base/SB2-1-plan-v1.md §6.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import ast
import pathlib

import pytest

import core.config as config
from core.config import _apply_profile_overrides
from core.profile_loader import (
    KARAOS_PROFILE,
    ProfileError,
    _resolve,
    _validate,
    load_profile,
)
from profiles._schema import (
    CLOUD_TIMING_MAP,
    FEATURE_FLAG_MAP,
    LLM_ROLES,
    PROVIDER_BUNDLES,
    SCHEMA,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
_CONFIG_PY = REPO_ROOT / "core" / "config.py"
_LOADER_PY = REPO_ROOT / "core" / "profile_loader.py"

# Try the P0.S6 env-access allowlist for T4's cross-check (import-mode agnostic).
try:
    from tests.test_secrets_invariants import _ENV_VAR_ACCESS_ALLOWLIST as _P0S6_ALLOW
except ImportError:  # pragma: no cover — pytest top-level import mode
    try:
        from test_secrets_invariants import _ENV_VAR_ACCESS_ALLOWLIST as _P0S6_ALLOW
    except ImportError:  # pragma: no cover
        _P0S6_ALLOW = {}


# ────────────────────────────────────────────────────────────────────────────
# shared helpers
# ────────────────────────────────────────────────────────────────────────────

def _overridable_leaf_keys() -> "set[str]":
    """The full set of config globals the apply writes (the override targets)."""
    keys: set[str] = set()
    for role in LLM_ROLES:
        p = role.upper()
        keys |= {f"{p}_MODEL", f"{p}_BASE_URL", f"{p}_API_KEY"}
    keys |= set(CLOUD_TIMING_MAP.values())
    keys |= set(FEATURE_FLAG_MAP.values())
    return keys


def _iter_module_level(tree: ast.Module):
    """Yield module-scope descendants, NOT descending into function/class scopes
    (so a function-internal assignment never pollutes the module-level analysis)."""
    stack = list(tree.body)
    _NESTED = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)
    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, _NESTED):
            continue
        stack.extend(ast.iter_child_nodes(node))


def _rhs_has_env_read(rhs: ast.AST) -> bool:
    """True if the expression contains an os.getenv / os.environ read."""
    for n in ast.walk(rhs):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
            f = n.func
            if isinstance(f.value, ast.Name) and f.value.id == "os" and f.attr == "getenv":
                return True
            if (isinstance(f.value, ast.Attribute) and isinstance(f.value.value, ast.Name)
                    and f.value.value.id == "os" and f.value.attr == "environ"):
                return True
        if isinstance(n, ast.Subscript):
            v = n.value
            if (isinstance(v, ast.Attribute) and isinstance(v.value, ast.Name)
                    and v.value.id == "os" and v.attr == "environ"):
                return True
    return False


def _env_taint_closure(source: str) -> "set[str]":
    """Transitive taint closure over config.py's MODULE-LEVEL assignments (PI-A):
    seed = LHS names of any assignment whose RHS reads os.getenv/os.environ;
    propagate = any assignment whose RHS references an already-tainted Name. This
    catches the `.strip()` intermediate (_TOGETHER_API_KEY_RAW → TOGETHER_API_KEY)
    AND the *_API_KEY leaves — NOT a literal 2-pattern scan (which skips the hop
    and would value-compare TOGETHER_API_KEY's resolved secret → a secret in the
    golden). The deterministic string-literal *_BASE_URL chain stays OUT (no env
    read → value-compared)."""
    tree = ast.parse(source)
    assigns: list[tuple[list[str], set[str], bool]] = []
    for node in _iter_module_level(tree):
        targets: list[str] = []
        rhs: ast.AST | None = None
        if isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            rhs = node.value
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name):
                targets = [node.target.id]
            rhs = node.value
        if not targets or rhs is None:
            continue
        refs = {n.id for n in ast.walk(rhs) if isinstance(n, ast.Name)}
        assigns.append((targets, refs, _rhs_has_env_read(rhs)))

    tainted: set[str] = set()
    for targets, _refs, has_env in assigns:
        if has_env:
            tainted.update(targets)
    changed = True
    while changed:
        changed = False
        for targets, refs, _has_env in assigns:
            if any(t in tainted for t in targets):
                continue
            if refs & tainted:
                tainted.update(targets)
                changed = True
    return tainted


def _scan_env_reads(tree: ast.AST) -> "list[tuple[int, str]]":
    """(lineno, var_name) for every os.getenv("X") / os.environ.get("X") /
    os.environ["X"] read with a literal string key."""
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            f = node.func
            is_getenv = isinstance(f.value, ast.Name) and f.value.id == "os" and f.attr == "getenv"
            is_environ_get = (isinstance(f.value, ast.Attribute)
                              and isinstance(f.value.value, ast.Name)
                              and f.value.value.id == "os" and f.value.attr == "environ"
                              and f.attr == "get")
            if (is_getenv or is_environ_get) and node.args:
                a0 = node.args[0]
                if isinstance(a0, ast.Constant) and isinstance(a0.value, str):
                    out.append((node.lineno, a0.value))
        if isinstance(node, ast.Subscript):
            v = node.value
            if (isinstance(v, ast.Attribute) and isinstance(v.value, ast.Name)
                    and v.value.id == "os" and v.attr == "environ"):
                k = node.slice
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    out.append((node.lineno, k.value))
    return out


def _find_attr_reassigns(source: str, names: "set[str]") -> "list[tuple[int, str]]":
    """(lineno, attr) for every `<x>.<NAME> = ...` Store assignment where NAME ∈ names."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        targets: list[ast.AST] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            targets = [node.target]
        for t in targets:
            if isinstance(t, ast.Attribute) and t.attr in names:
                hits.append((node.lineno, t.attr))
    return hits


def _runtime_production_files() -> "list[pathlib.Path]":
    """pipeline.py + core/ (excl _minifasnet) + runtime/ + flows/ + profiles/."""
    files: list[pathlib.Path] = [REPO_ROOT / "pipeline.py"]
    for p in sorted((REPO_ROOT / "core").rglob("*.py")):
        if "_minifasnet" not in p.parts:
            files.append(p)
    for sub in ("runtime", "flows", "profiles"):
        files.extend(sorted((REPO_ROOT / sub).rglob("*.py")))
    return [f for f in files if f.is_file()]


def _p0s6_scope_files() -> "list[pathlib.Path]":
    """T4 uses P0.S6's env-centralization scope: core/ + pipeline.py + enroll.py."""
    files: list[pathlib.Path] = []
    for p in sorted((REPO_ROOT / "core").rglob("*.py")):
        files.append(p)
    for name in ("pipeline.py", "enroll.py"):
        p = REPO_ROOT / name
        if p.is_file():
            files.append(p)
    return files


def _profile_axis_env_vars() -> "set[str]":
    """Env-var NAMES a profile axis resolves to (the non-empty api_key_env values)."""
    return {leaf["api_key_env"]
            for bundle in PROVIDER_BUNDLES.values()
            for leaf in bundle.values()
            if leaf["api_key_env"]}


# Committed golden: today's values for the NON-env-tainted overridable leaves.
# The *_API_KEY leaves are deliberately ABSENT (env-tainted → excluded → never a
# secret in the golden). A drift in any of these == a behavior change.
_T1_GOLDEN: "dict[str, object]" = {
    "CHAT_MODEL": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
    "CHAT_BASE_URL": "https://api.together.xyz/v1",
    "EXTRACT_MODEL": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
    "EXTRACT_BASE_URL": "https://api.together.xyz/v1",
    "EMBED_MODEL": "intfloat/multilingual-e5-large-instruct",
    "EMBED_BASE_URL": "https://api.together.xyz/v1",
    "VISION_MODEL": "Qwen/Qwen3-VL-8B-Instruct",
    "VISION_BASE_URL": "https://api.together.xyz/v1",
    "CLOUD_OFFLINE_TIMEOUT": 120,
    "CLOUD_RETRY_INTERVAL": 30,
    "EMOTION_ENABLED": True,
    "CORE_MEMORY_ENABLED": True,
}


# ────────────────────────────────────────────────────────────────────────────
# T1 — golden snapshot (PI-2 override-layer + PI-A taint closure)
# ────────────────────────────────────────────────────────────────────────────

def test_t1_golden_snapshot_companion_is_behavior_neutral() -> None:
    """T1 — apply(companion) == today's base for every non-env-tainted overridable
    leaf. Env-derived keys excluded via the transitive taint closure (PI-A); the
    *_API_KEY leaves are never value-compared (no secret in the golden)."""
    if KARAOS_PROFILE != "companion":
        pytest.skip(f"T1 asserts the default companion profile; KARAOS_PROFILE={KARAOS_PROFILE!r}")

    taint = _env_taint_closure(_CONFIG_PY.read_text(encoding="utf-8"))
    # PI-A self-test: the closure catches the .strip() hop + the leaves, NOT just
    # the 2 root patterns.
    assert "_TOGETHER_API_KEY_RAW" in taint
    assert "TOGETHER_API_KEY" in taint, "taint closure must include the .strip() intermediate"
    for role in LLM_ROLES:
        assert f"{role.upper()}_API_KEY" in taint, "each *_API_KEY leaf must be excluded (no secret in golden)"

    checkable = _overridable_leaf_keys() - taint
    assert checkable == set(_T1_GOLDEN), (
        "the non-env-tainted overridable leaf set drifted from the committed golden — "
        f"checkable={sorted(checkable)} golden={sorted(_T1_GOLDEN)}"
    )
    for key, expected in _T1_GOLDEN.items():
        actual = getattr(config, key)
        assert actual == expected and type(actual) is type(expected), (
            f"companion behavior-neutrality broken: config.{key}={actual!r} != golden {expected!r}"
        )


def test_t1_taint_closure_self_test() -> None:
    """The taint closure seeds on env reads + propagates transitively (incl. the
    .strip() hop), and leaves a deterministic string-literal chain OUT."""
    src = (
        "import os\n"
        "_RAW = os.getenv('K', '')\n"
        "KEY = _RAW.strip()\n"
        "CHILD = KEY\n"
        "BASE = 'https://x/v1'\n"
        "CHILD_BASE = BASE\n"
    )
    taint = _env_taint_closure(src)
    assert {"_RAW", "KEY", "CHILD"} <= taint
    assert "BASE" not in taint and "CHILD_BASE" not in taint


# ────────────────────────────────────────────────────────────────────────────
# T2 — derived-constant-consistency (PI-1) + strip (PI-C)
# ────────────────────────────────────────────────────────────────────────────

def test_t2_provider_flip_writes_clean_leaves_no_stale_cloud() -> None:
    """T2 — a synthetic provider-flip writes every *_MODEL/*_BASE_URL/*_API_KEY
    leaf from the declared provider, zero stale-cloud leak (PI-1: leaf-level)."""
    synthetic = {
        "profile": "companion",
        "llm": {
            "chat":    {"model": "local-chat-m", "base_url": "http://local/v1", "api_key_env": ""},
            "extract": {"model": "local-extract-m", "base_url": "http://local/v1", "api_key_env": ""},
            "embed":   {"model": "local-embed-m", "base_url": "http://local/v1", "api_key_env": ""},
            "vision":  {"model": "local-vision-m", "base_url": "http://local/v1", "api_key_env": ""},
            "cloud":   {"offline_timeout": 99, "retry_interval": 7},
        },
    }
    _validate(synthetic, "companion", "<synthetic>")
    resolved = _resolve(synthetic)
    g: dict = {}
    _apply_profile_overrides(g, resolved)

    for role in LLM_ROLES:
        p = role.upper()
        assert g[f"{p}_MODEL"] == f"local-{role}-m"
        assert g[f"{p}_BASE_URL"] == "http://local/v1"
        assert g[f"{p}_API_KEY"] == ""  # keyless local
    assert g["CLOUD_OFFLINE_TIMEOUT"] == 99 and g["CLOUD_RETRY_INTERVAL"] == 7

    cloud_models = {leaf["model"] for leaf in PROVIDER_BUNDLES["cloud"].values()}
    for role in LLM_ROLES:
        p = role.upper()
        assert g[f"{p}_MODEL"] not in cloud_models, "stale cloud model leaked into a leaf"
        assert g[f"{p}_BASE_URL"] != "https://api.together.xyz/v1", "stale cloud base_url leaked"


def test_t2_padded_api_key_is_stripped(monkeypatch) -> None:
    """T2/PI-C — the api_key leaf is re-resolved via os.getenv(name).strip(), so a
    whitespace-padded key never leaks raw into Authorization: Bearer (P0.S3)."""
    monkeypatch.setenv("SB21_T2_PADDED_KEY", "  sk-padded-xyz  ")
    synthetic = {
        "profile": "companion",
        "llm": {"chat": {"model": "m", "base_url": "http://x/v1", "api_key_env": "SB21_T2_PADDED_KEY"}},
    }
    _validate(synthetic, "companion", "<synthetic>")
    g: dict = {}
    _apply_profile_overrides(g, _resolve(synthetic))
    assert g["CHAT_API_KEY"] == "sk-padded-xyz"
    assert g["CHAT_API_KEY"] == g["CHAT_API_KEY"].strip()


# ────────────────────────────────────────────────────────────────────────────
# T3 — no-late-mutation
# ────────────────────────────────────────────────────────────────────────────

def test_t3_no_late_mutation_of_overridable_keys() -> None:
    """T3 — no production code reassigns a profile-overridable config key
    (`config.CHAT_MODEL = ...`) after config-module-init. config.py's own writes
    are bare-Name / globals()-subscript (not Attribute targets) → not flagged."""
    overridable = _overridable_leaf_keys()
    violations: list[str] = []
    for path in _runtime_production_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        for lineno, attr in _find_attr_reassigns(path.read_text(encoding="utf-8"), overridable):
            violations.append(f"{rel}:{lineno} reassigns .{attr}")
    assert violations == [], (
        "T3 — profile-overridable config keys must never be reassigned post-init "
        "(the from-import value would diverge):\n" + "\n".join(violations)
    )


def test_t3_self_test_attr_reassign_detected() -> None:
    """Forward self-test: a synthetic `config.CHAT_MODEL = 'x'` IS detected."""
    src = "import core.config as config\nconfig.CHAT_MODEL = 'x'\n"
    hits = _find_attr_reassigns(src, {"CHAT_MODEL"})
    assert hits == [(2, "CHAT_MODEL")]


# ────────────────────────────────────────────────────────────────────────────
# T4 — no config-bypassing lazy reader (PI-1 sub; PI-B)
# ────────────────────────────────────────────────────────────────────────────

def test_t4_no_config_bypassing_reader_for_profile_axis_env_vars() -> None:
    """T4 — no SB.2.1 profile-axis env var (the api_key_env NAMES) is read via a
    config-bypassing os.getenv/os.environ in P0.S6 scope (core/ + pipeline +
    enroll), unless allowlisted. PI-B: the known bypass readers HF_TOKEN /
    HUGGING_FACE_HUB_TOKEN (core/heavy_worker.py) are confirmed NOT profile axes."""
    axis_vars = _profile_axis_env_vars()
    assert axis_vars == {"TOGETHER_API_KEY"}, f"unexpected profile-axis env vars: {axis_vars}"
    assert "HF_TOKEN" not in axis_vars
    assert "HUGGING_FACE_HUB_TOKEN" not in axis_vars

    violations: list[str] = []
    for path in _p0s6_scope_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel == "core/config.py":  # the centralized read site — exempt
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for lineno, var in _scan_env_reads(tree):
            if var in axis_vars and (rel, var, "read") not in _P0S6_ALLOW:
                violations.append(f"{rel}:{lineno} config-bypassing read of profile-axis env var {var!r}")
    assert violations == [], (
        "T4 — a profile-axis env var is read outside config.py (the override would "
        "not reach this consumer); centralize it or allowlist it:\n" + "\n".join(violations)
    )


# ────────────────────────────────────────────────────────────────────────────
# T5 — schema fail-loud (parametrized)
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("case", [
    "unknown_profile", "unknown_section", "unknown_key",
    "bad_type", "bad_enum", "bad_leaf_type",
])
def test_t5_schema_fail_loud(case: str) -> None:
    """T5 — every malformed profile input fail-louds with a clear ProfileError."""
    if case == "unknown_profile":
        with pytest.raises(ProfileError):
            load_profile("nonexistent_profile_xyz")
    elif case == "unknown_section":
        with pytest.raises(ProfileError):
            _validate({"profile": "companion", "wat": {}}, "companion", "<t5>")
    elif case == "unknown_key":
        with pytest.raises(ProfileError):
            _validate({"profile": "companion", "features": {"not_a_feature": True}}, "companion", "<t5>")
    elif case == "bad_type":
        with pytest.raises(ProfileError):
            _validate({"profile": "companion", "features": {"emotion": "yes"}}, "companion", "<t5>")
    elif case == "bad_enum":
        with pytest.raises(ProfileError):
            _validate({"profile": "companion", "llm": {"provider": "banana"}}, "companion", "<t5>")
    elif case == "bad_leaf_type":
        with pytest.raises(ProfileError):
            _validate({"profile": "companion", "llm": {"chat": {"model": 123}}}, "companion", "<t5>")


# ────────────────────────────────────────────────────────────────────────────
# T6 — robotics loads + applies (no silent cloud fallback)
# ────────────────────────────────────────────────────────────────────────────

def test_t6_robotics_loads_and_applies() -> None:
    """T6 — KARAOS_PROFILE=robotics → local-LLM leaves + disabled feature flags
    applied, no crash."""
    overrides = load_profile("robotics")
    g: dict = {}
    _apply_profile_overrides(g, overrides)
    for role in LLM_ROLES:
        p = role.upper()
        assert g[f"{p}_MODEL"] == PROVIDER_BUNDLES["local-orin"][role]["model"]
        assert g[f"{p}_BASE_URL"] == PROVIDER_BUNDLES["local-orin"][role]["base_url"]
        assert g[f"{p}_API_KEY"] == ""  # keyless local
    assert g["EMOTION_ENABLED"] is False
    assert g["CORE_MEMORY_ENABLED"] is False


def test_t6_no_silent_cloud_fallback_on_unknown_bundle() -> None:
    """T6 RED-shape — an unknown provider RAISES; it must NEVER silently fall back
    to the cloud bundle."""
    with pytest.raises(ProfileError):
        _resolve({"profile": "robotics", "llm": {"provider": "nonexistent-bundle"}})


# ────────────────────────────────────────────────────────────────────────────
# T7 — feature-toggle keys map to real config flags
# ────────────────────────────────────────────────────────────────────────────

def test_t7_feature_keys_map_to_real_config_flags() -> None:
    """T7 — every features.* schema key maps 1:1 to an existing config.*_ENABLED
    flag (a not-yet-flagged toggle is NOT in the SB.2.1 schema — fail-loud)."""
    assert set(SCHEMA["features"]["keys"]) == set(FEATURE_FLAG_MAP), (
        "every features.* schema key must have a FEATURE_FLAG_MAP entry"
    )
    for feat, flag in FEATURE_FLAG_MAP.items():
        assert hasattr(config, flag), (
            f"features.{feat} → config.{flag} which does NOT exist; a not-yet-flagged "
            f"toggle must not be in the SB.2.1 schema"
        )
        assert isinstance(getattr(config, flag), bool), f"config.{flag} must be a bool flag"


# ────────────────────────────────────────────────────────────────────────────
# T8 — no import cycle (loader is config-free)
# ────────────────────────────────────────────────────────────────────────────

def test_t8_loader_has_no_core_config_import() -> None:
    """T8 — core/profile_loader.py imports nothing from core.config (no cycle:
    config imports the loader at its end, never vice versa)."""
    tree = ast.parse(_LOADER_PY.read_text(encoding="utf-8"))
    bad: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name == "core.config" or a.name.startswith("core.config."):
                    bad.append(f"line {node.lineno}: import {a.name}")
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod == "core.config" or mod.startswith("core.config."):
                bad.append(f"line {node.lineno}: from {mod} import ...")
    assert bad == [], f"profile_loader must not import core.config (import cycle): {bad}"
