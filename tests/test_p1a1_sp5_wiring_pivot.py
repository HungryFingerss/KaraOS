"""P1.A1 SP-5 — the wiring-pivot invariants (the make-or-break, RED-gated).

Three places a rebound-global facade silently rots, each pinned here:

  R2 write-completeness — no `pipeline.<5-name> = ` survives (would create a real
    pipeline attr that SHADOWS the __getattr__ facade; silent desync). RED-probe:
    inject `pipeline._session_store = X` -> test_sp5_write_completeness fires.

  R2 read-completeness — zero bare `Name(id in 5)` in pipeline.py (a missed internal
    read is a NameError on an un-exercised god-function branch — canary-blind until
    the hardware run). This static scan pins it suite-covered. RED-probe: leave one
    bare read unrewired -> test_sp5_read_completeness fires.

  Reset-propagation — rebinding the canonical home (`_wiring._session_store`) is seen
    by the facade as the FRESH instance (a blanket from-import would snapshot the
    stale one). RED-probe: make __getattr__ return a stale snapshot -> this fires.

The __getattr__ whitelist must be EXACTLY the 5 rebound names (broaden it -> typos
masked + the conftest reset fixture's hasattr(pipeline, …) perturbed).
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

import ast
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

THE_5 = frozenset({
    "_session_store", "_pipeline_state_store", "_brain_orchestrator",
    "_face_db_ref", "_room_orchestrator",
})
PIPELINE_ALIASES = {"pipeline", "_pl", "_pipeline"}

_ALIAS_RE = r"(?:pipeline|_pl|_pipeline)"
_NAMES_RE = "|".join(sorted(THE_5))
# patch-shadow forms — mock.patch/patch.object/monkeypatch.setattr that setattr a
# REAL pipeline.<5-name> attr, shadowing __getattr__ (the rewired read hits _wiring._X,
# so these MUST target runtime.wiring._X). These are facade-shadowing WRITES that the
# AST assignment-scan does NOT see (they're Calls). The kairos failure was exactly this.
_PATCH_SHADOW_RE = re.compile(
    rf'patch\(\s*["\']{_ALIAS_RE}\.(?:{_NAMES_RE})["\']'                       # patch("pipeline._X"
    rf'|patch\.object\(\s*{_ALIAS_RE}\s*,\s*["\'](?:{_NAMES_RE})["\']'         # patch.object(pipeline, "_X"
    rf'|setattr\(\s*{_ALIAS_RE}\s*,\s*["\'](?:{_NAMES_RE})["\']'               # (monkeypatch.)setattr(pipeline, "_X"
)

# files that legitimately rebind the canonical home (must target _wiring, NOT pipeline)
_WRITE_SCAN_FILES = (
    [REPO_ROOT / "pipeline.py", REPO_ROOT / "sim_runner.py", REPO_ROOT / "conftest.py"]
    + sorted((REPO_ROOT / "tests").glob("*.py"))
)


def _pipeline_tree() -> ast.Module:
    return ast.parse((REPO_ROOT / "pipeline.py").read_text(encoding="utf-8"))


def test_sp5_getattr_whitelist_is_exactly_the_5_rebound():
    """R2 — `_WIRING_FORWARDED` (the __getattr__ whitelist) is EXACTLY the 5 rebound names."""
    forwarded = None
    for node in ast.walk(_pipeline_tree()):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "_WIRING_FORWARDED" for t in node.targets
        ):
            forwarded = {
                c.value for c in ast.walk(node.value)
                if isinstance(c, ast.Constant) and isinstance(c.value, str)
            }
    assert forwarded is not None, "pipeline.py must define _WIRING_FORWARDED (the __getattr__ whitelist)"
    assert forwarded == set(THE_5), (
        f"__getattr__ whitelist drift: {sorted(forwarded)} != {sorted(THE_5)}. "
        f"Broadening masks typos and perturbs the reset fixture's hasattr(pipeline, …)."
    )


def test_sp5_read_completeness_no_bare_rebound_name_in_pipeline():
    """R2 read-completeness — zero bare `Name(id in 5)` in pipeline.py. Every internal
    ref must be `_wiring._X` (an Attribute whose value-Name is `_wiring`) or a whitelist
    string-literal (Constant). A surviving bare read is a canary-blind NameError."""
    bare = [
        (n.lineno, n.id) for n in ast.walk(_pipeline_tree())
        if isinstance(n, ast.Name) and n.id in THE_5
    ]
    assert not bare, (
        f"bare rebound-global reads survive in pipeline.py (must be _wiring._X): {bare[:12]}"
    )


def test_sp5_write_completeness_no_facade_shadowing_assignment():
    """R2 write-completeness — no file assigns `<pipeline-alias>.<5-name> = ...`, which
    would create a real pipeline attr shadowing the __getattr__ facade. Every rebind
    must target `_wiring._X`. AST-based (immune to string/comment false-positives)."""
    offenders = []
    for path in _WRITE_SCAN_FILES:
        if path.name == Path(__file__).name:
            continue  # don't scan this test's own source
        try:
            text = path.read_text(encoding="utf-8")
            tree = ast.parse(text)
        except (SyntaxError, FileNotFoundError):
            continue
        # (a) assignment-LHS shadows: `pipeline._X = ...`
        for node in ast.walk(tree):
            targets = []
            if isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, ast.AnnAssign):
                targets = [node.target]
            for t in targets:
                if (isinstance(t, ast.Attribute) and t.attr in THE_5
                        and isinstance(t.value, ast.Name) and t.value.id in PIPELINE_ALIASES):
                    offenders.append(f"{path.name}:{node.lineno} ({t.value.id}.{t.attr} = ...)")
        # (b) patch-shadows: patch("pipeline._X")/patch.object(pipeline,"_X")/setattr(pipeline,"_X")
        for i, line in enumerate(text.splitlines(), 1):
            if _PATCH_SHADOW_RE.search(line):
                offenders.append(f"{path.name}:{i} (patch-shadow: {line.strip()[:60]})")
    assert not offenders, (
        f"surviving facade-shadowing writes to pipeline.<5-name> (assignment OR "
        f"patch/setattr) — retarget to _wiring._X / runtime.wiring._X: {offenders}"
    )


def test_sp5_reset_propagation_facade_resolves_to_fresh_instance():
    """SP-5 cross-module reset-propagation — rebinding the canonical home is seen by the
    pipeline.__getattr__ facade as the FRESH instance (the proof a from-import snapshot
    would FAIL). Also exercises set_brain_orchestrator() — the ratified canonical-home
    setter. RED-probe: a stale-snapshot __getattr__ fails the first assert."""
    import runtime.wiring as wiring
    import pipeline

    sentinel_ss = object()
    sentinel_bo = object()
    old_ss = wiring._session_store
    old_bo = wiring._brain_orchestrator
    try:
        # rebind the canonical home directly
        wiring._session_store = sentinel_ss
        assert pipeline._session_store is sentinel_ss, (
            "pipeline.__getattr__ facade resolved to a STALE _session_store, not the "
            "fresh _wiring instance — a from-import snapshot bug."
        )
        # the ratified helper also routes through the canonical home
        wiring.set_brain_orchestrator(sentinel_bo)
        assert wiring._brain_orchestrator is sentinel_bo
        assert pipeline._brain_orchestrator is sentinel_bo, (
            "set_brain_orchestrator() not visible via the pipeline facade."
        )
    finally:
        wiring._session_store = old_ss
        wiring._brain_orchestrator = old_bo


def test_sp5_getattr_rejects_non_whitelisted_name():
    """The whitelist is STRICT — a non-rebound name raises AttributeError (typos not
    masked; hasattr(pipeline, <typo>) stays False)."""
    import pipeline
    with pytest.raises(AttributeError):
        _ = pipeline._this_name_does_not_exist_sp5
