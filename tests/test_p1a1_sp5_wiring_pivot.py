"""P1.A1 SP-5 + SP-6.3 — the wiring-pivot invariants (the make-or-break, RED-gated).

Three places a wired-global facade silently rots, each pinned here:

  R2 write-completeness — no `pipeline.<wired-name> = ` / `patch("pipeline._X")` survives
    (would create a real pipeline attr that SHADOWS the __getattr__ facade; the rewired
    read hits `_wiring._X`, so the shadow is silently ignored — desync). RED-probe:
    inject `pipeline._session_store = X` -> test_sp5_write_completeness fires.

  R2 read-completeness — zero bare `Name(id in WIRED)` in pipeline.py AND runtime/vision_loop.py
    (a missed internal read is a NameError on an un-exercised branch — canary-blind until the
    hardware run). Static scan pins it suite-covered. RED-probe: leave one bare read unrewired.

  Reset-propagation — rebinding the canonical home (`_wiring._session_store`) is seen by the
    facade as the FRESH instance (a blanket from-import would snapshot the stale one).

The __getattr__ whitelist must be EXACTLY the N forwarded names — the 5 SP-5 rebound globals
+ the 2 SP-6.3 test-read WIRE-d vision globals (_anti_spoof_checker, _vision_task). The 2
SP-6.3 heartbeats are WIRE-d (internal reads rewired to _wiring._X) but NOT forwarded (no
external pipeline._X read), so they're in the read-completeness scan but NOT the whitelist.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

import ast
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# SP-5 rebound globals (canonical home = runtime.wiring; facade-forwarded)
THE_5 = frozenset({
    "_session_store", "_pipeline_state_store", "_brain_orchestrator",
    "_face_db_ref", "_room_orchestrator",
})
# SP-6.3 WIRE-d vision globals that are ALSO externally read (test-read) -> facade-forwarded
SP63_FORWARDED = frozenset({"_anti_spoof_checker", "_vision_task"})
# SP-6.3 WIRE-d vision globals read+written ONLY internally (run + vision_loop) -> NOT forwarded
SP63_INTERNAL = frozenset({"_vision_last_heartbeat", "_vision_last_heartbeat_state"})

# the __getattr__ whitelist == every facade-forwarded name (5 + 2)
FORWARDED = THE_5 | SP63_FORWARDED
# read-completeness scan set == EVERY wired global (no bare Name anywhere) (5 + 4)
WIRED_ALL = THE_5 | SP63_FORWARDED | SP63_INTERNAL

PIPELINE_ALIASES = {"pipeline", "_pl", "_pipeline"}
_ALIAS_RE = r"(?:pipeline|_pl|_pipeline)"
_NAMES_RE = "|".join(sorted(FORWARDED))
# patch-shadow forms — patch/patch.object/setattr that setattr a REAL pipeline.<forwarded>
# attr, shadowing __getattr__ (the rewired read hits _wiring._X, so these MUST target
# runtime.wiring._X). AST assignment-scan does NOT see these (they're Calls).
_PATCH_SHADOW_RE = re.compile(
    rf'patch\(\s*["\']{_ALIAS_RE}\.(?:{_NAMES_RE})["\']'
    rf'|patch\.object\(\s*{_ALIAS_RE}\s*,\s*["\'](?:{_NAMES_RE})["\']'
    rf'|setattr\(\s*{_ALIAS_RE}\s*,\s*["\'](?:{_NAMES_RE})["\']'
)

_WRITE_SCAN_FILES = (
    [REPO_ROOT / "pipeline.py", REPO_ROOT / "sim_runner.py", REPO_ROOT / "conftest.py"]
    + sorted((REPO_ROOT / "tests").glob("*.py"))
)
_READ_SCAN_FILES = [REPO_ROOT / "pipeline.py", REPO_ROOT / "runtime" / "vision_loop.py"]


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def test_sp5_getattr_whitelist_is_exactly_the_N_forwarded():
    """R2 — `_WIRING_FORWARDED` (the __getattr__ whitelist) is EXACTLY the N forwarded
    names (5 SP-5 rebound + 2 SP-6.3 test-read WIRE-d). Broadening masks typos + perturbs
    the reset fixture's hasattr(pipeline, …); narrowing breaks an external pipeline._X read."""
    forwarded = None
    for node in ast.walk(_tree(REPO_ROOT / "pipeline.py")):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "_WIRING_FORWARDED" for t in node.targets
        ):
            forwarded = {
                c.value for c in ast.walk(node.value)
                if isinstance(c, ast.Constant) and isinstance(c.value, str)
            }
    assert forwarded is not None, "pipeline.py must define _WIRING_FORWARDED (the __getattr__ whitelist)"
    assert forwarded == set(FORWARDED), (
        f"__getattr__ whitelist drift: {sorted(forwarded)} != {sorted(FORWARDED)}. "
        f"Whitelist must be the 5 SP-5 rebound + 2 SP-6.3 test-read (_anti_spoof_checker, _vision_task)."
    )


def test_sp5_read_completeness_no_bare_wired_name_in_engine():
    """R2 read-completeness — zero bare `Name(id in WIRED_ALL)` in pipeline.py AND
    runtime/vision_loop.py. Every internal ref must be `_wiring._X`. A surviving bare read
    is a canary-blind NameError (the SP-6.3 heartbeats are NOT facade-forwarded, so a missed
    bare read of them would NOT even be caught by __getattr__ — pure NameError)."""
    bare = []
    for path in _READ_SCAN_FILES:
        for n in ast.walk(_tree(path)):
            if isinstance(n, ast.Name) and n.id in WIRED_ALL:
                bare.append(f"{path.name}:{n.lineno} ({n.id})")
    assert not bare, (
        f"bare wired-global reads survive (must be _wiring._X): {bare[:12]}"
    )


def test_sp5_write_completeness_no_facade_shadowing_assignment():
    """R2 write-completeness — no file assigns/patches `<pipeline-alias>.<forwarded-name>`,
    which would create a real pipeline attr shadowing the __getattr__ facade. Every rebind
    must target `_wiring._X` / `runtime.wiring._X`. AST + regex (string-immune for the assign)."""
    offenders = []
    for path in _WRITE_SCAN_FILES:
        if path.name == Path(__file__).name:
            continue
        try:
            text = path.read_text(encoding="utf-8")
            tree = ast.parse(text)
        except (SyntaxError, FileNotFoundError):
            continue
        for node in ast.walk(tree):
            targets = node.targets if isinstance(node, ast.Assign) else (
                [node.target] if isinstance(node, ast.AnnAssign) else [])
            for t in targets:
                if (isinstance(t, ast.Attribute) and t.attr in FORWARDED
                        and isinstance(t.value, ast.Name) and t.value.id in PIPELINE_ALIASES):
                    offenders.append(f"{path.name}:{node.lineno} ({t.value.id}.{t.attr} = ...)")
        for i, line in enumerate(text.splitlines(), 1):
            if _PATCH_SHADOW_RE.search(line):
                offenders.append(f"{path.name}:{i} (patch-shadow: {line.strip()[:60]})")
    assert not offenders, (
        f"surviving facade-shadowing writes to pipeline.<forwarded-name> (assignment OR "
        f"patch/setattr) — retarget to _wiring._X / runtime.wiring._X: {offenders}"
    )


def test_sp5_reset_propagation_facade_resolves_to_fresh_instance():
    """SP-5 + SP-6.3 cross-module reset-propagation — rebinding the canonical home is seen by
    pipeline.__getattr__ as the FRESH instance (the proof a from-import snapshot would FAIL).
    Covers an SP-5 rebound (_session_store), set_brain_orchestrator(), AND an SP-6.3 WIRE-d
    forward (_anti_spoof_checker)."""
    import runtime.wiring as wiring
    import pipeline

    sentinel_ss, sentinel_bo, sentinel_as = object(), object(), object()
    old_ss = wiring._session_store
    old_bo = wiring._brain_orchestrator
    old_as = wiring._anti_spoof_checker
    try:
        wiring._session_store = sentinel_ss
        assert pipeline._session_store is sentinel_ss, (
            "pipeline.__getattr__ resolved a STALE _session_store — a from-import snapshot bug."
        )
        wiring.set_brain_orchestrator(sentinel_bo)
        assert pipeline._brain_orchestrator is sentinel_bo, (
            "set_brain_orchestrator() not visible via the pipeline facade."
        )
        wiring._anti_spoof_checker = sentinel_as
        assert pipeline._anti_spoof_checker is sentinel_as, (
            "SP-6.3: pipeline.__getattr__ did not forward _anti_spoof_checker to the fresh "
            "runtime.wiring instance — the facade whitelist is missing it."
        )
    finally:
        wiring._session_store = old_ss
        wiring._brain_orchestrator = old_bo
        wiring._anti_spoof_checker = old_as


def test_sp5_getattr_rejects_non_whitelisted_name():
    """The whitelist is STRICT — a non-forwarded name raises AttributeError (typos not
    masked; hasattr(pipeline, <typo>) stays False)."""
    import pipeline
    with pytest.raises(AttributeError):
        _ = pipeline._this_name_does_not_exist_sp5
