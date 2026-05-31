"""Follow-up #126 — systemic `@pytest.mark.real_voice` golden-test vacuity guard.

The LAST spec of the post-canary arc (#129 → #123 → #128 → #126). Generalizes the Canary #3
lesson into a project-wide convention: a real-voice golden test must provably exercise the
REAL `core.voice` module, never the autouse conftest stub (whose `embed → None` /
`identify → (None, …)` make a naive "real behavior" assertion vacuous — a permanent false-RED
that hid the Canary #3 embed-None bug for a week).

D4 are the systemic tripwires (the core preventive value). PI (mandatory, #123 PI-1 / #128 D1
discipline): each detector is ONE shared source-string helper that BOTH the forward test (real
`tests/` files) AND the self-tests (synthetic sources) route through — so the self-tests
validate the SAME detector that scans production. #126's own detector must not be vacuous about
a vacuity guard.

D5 is the BEHAVIORAL stub-fail-loud lock (Q3): the vacuity guard's leverage is that the stub
returns FALSY. A stub mutated truthy would make a fixture-less real-voice test permanent-GREEN —
silently passing against a mock, the one regime D1-D4 can't see. D5 keeps vacuity catchable by
asserting the INSTALLED stub's runtime falsy return.

Scoping caveats (#123 D2b in-code-documentation precedent):
  - D4(a) MECHANISM scope (Q4): the detector matches `importlib.import_module("core.voice")`
    by EXACT string. A test real-importing via `__import__("core.voice")` OR
    `sys.modules.pop("core.voice")` + a PLAIN `import core.voice` statement would be missed (the
    pop-then-plain-import compound is hard to AST-detect robustly). Scope to the
    `importlib.import_module` shape the project uses; note the assumption rather than chase every
    mechanism. (The blessed fixture's teardown does pop + restore-stub — a RESTORE, not a
    pop-then-real-import — and tests/conftest.py is excluded regardless.)
  - D5 is BEHAVIORAL, not structural (Q3) — it tests the installed stub's runtime falsy return,
    robust to a semantically-equivalent refactor (`AsyncMock(return_value=None)` →
    `async def embed(...): return None`); no AsyncMock-shape caveat needed.

Spec: tests/followup126_real_voice_vacuity_guard_spec.md.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent          # tests/
_REPO_ROOT = _TESTS_DIR.parent
_BLESSED_CONFTEST = (_TESTS_DIR / "conftest.py").resolve()


# ══════════════════════════════════════════════════════════════════════════
# Shared detector helpers (PI — forward test + self-tests both route here)
# ══════════════════════════════════════════════════════════════════════════


def _core_voice_force_imports(source: str) -> list[int]:
    """#126 D4(a) shared helper — line numbers of `importlib.import_module("core.voice")`
    calls in `source`, matched by EXACT string `== "core.voice"`.

    Q4: exact-string, NOT prefix / `in` / `startswith` — `"core.voice_channel"` (a different
    module, real-imported at test_voice_channel.py) is a legitimate import a loose check would
    false-flag. See the D4(a) MECHANISM caveat in the module docstring for what this does NOT
    catch (`__import__` / pop-then-plain-import)."""
    tree = ast.parse(source)
    hits: list[int] = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        is_import_module = (
            (isinstance(f, ast.Attribute) and f.attr == "import_module")
            or (isinstance(f, ast.Name) and f.id == "import_module")
        )
        if not is_import_module or len(n.args) != 1:
            continue
        arg = n.args[0]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and arg.value == "core.voice":
            hits.append(n.lineno)
    return hits


def _real_voice_fixture_missing_guard(source: str) -> list[str]:
    """#126 D4(b) shared helper — returns ["real_voice"] if a `real_voice` fixture in `source`
    lacks the `_load_ecapa_patched` vacuity-guard assert, else []. The guard is what stops the
    fixture silently falling back to the stub (the exact Canary #3 vacuity)."""
    tree = ast.parse(source)
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef) and n.name == "real_voice":
            has_guard = any(
                isinstance(s, ast.Assert) and "_load_ecapa_patched" in ast.unparse(s)
                for s in ast.walk(n)
            )
            return [] if has_guard else ["real_voice"]
    return []  # no real_voice fixture in this source — not this helper's concern


def _real_voice_requesters_missing_marker(source: str) -> list[str]:
    """#126 D4(b) shared helper — names of test functions in `source` that request the
    `real_voice` fixture (param) but are NOT @pytest.mark.real_voice-marked (function decorator
    OR module-level `pytestmark`). Discoverability: a real-voice test must be greppable +
    `-m real_voice`-selectable."""
    tree = ast.parse(source)
    module_marked = any(
        isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in n.targets)
        and "real_voice" in ast.unparse(n.value)
        for n in tree.body
    )
    offenders: list[str] = []
    for n in ast.walk(tree):
        if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not n.name.startswith("test_"):
            continue
        if "real_voice" not in {a.arg for a in n.args.args}:
            continue
        decorated = any("real_voice" in ast.unparse(d) for d in n.decorator_list)
        if not (module_marked or decorated):
            offenders.append(n.name)
    return offenders


def _scanned_test_files() -> list[Path]:
    """Every `*.py` under tests/ (recursive) + the repo-root conftest.py, EXCLUDING only the
    blessed `tests/conftest.py` (Q1 — exclude the exact path, NOT the `conftest.py` basename,
    so an unguarded force-import in the ROOT conftest is still caught)."""
    files = sorted(_TESTS_DIR.rglob("*.py"))
    root_conftest = _REPO_ROOT / "conftest.py"
    if root_conftest.exists():
        files.append(root_conftest)
    return [f for f in files if f.resolve() != _BLESSED_CONFTEST]


# ══════════════════════════════════════════════════════════════════════════
# D4(a) — force-import only in the blessed fixture
# ══════════════════════════════════════════════════════════════════════════


def test_d4a_no_adhoc_core_voice_force_import_outside_blessed_fixture():
    """D4(a) forward — NO `importlib.import_module("core.voice")` anywhere in tests/ (or the
    root conftest) except the blessed `tests/conftest.py` real_voice fixture. A future golden
    test that hand-rolls the force-import would reinvent the unguarded path that hid Canary #3;
    it must request the shared `real_voice` fixture instead."""
    offenders: list[str] = []
    for f in _scanned_test_files():
        for ln in _core_voice_force_imports(f.read_text(encoding="utf-8")):
            offenders.append(f"{f.relative_to(_REPO_ROOT).as_posix()}:{ln}")
    assert offenders == [], (
        f"ad-hoc `importlib.import_module(\"core.voice\")` force-import(s) outside the blessed "
        f"tests/conftest.py fixture: {offenders}. Real-voice tests MUST request the shared "
        f"`real_voice` fixture (its `_load_ecapa_patched` assert is the vacuity guard) — a "
        f"hand-rolled force-import can silently test the stub (the Canary #3 false-RED class)."
    )


def test_d4a_self_test_core_voice_flagged():
    """D4(a) self-test — a synthetic `importlib.import_module("core.voice")` IS flagged.
    Routes through the same helper the forward test uses (#123 PI-1 / #128 D1)."""
    src = 'import importlib\nimportlib.import_module("core.voice")\n'
    assert _core_voice_force_imports(src) == [2]


def test_d4a_self_test_core_voice_channel_not_flagged():
    """D4(a) self-test — `importlib.import_module("core.voice_channel")` is NOT flagged
    (Q4: a real different-module import; the exact-string guard must not false-flag it)."""
    src = 'import importlib\nimportlib.import_module("core.voice_channel")\n'
    assert _core_voice_force_imports(src) == []


def test_d4a_self_test_stub_install_not_flagged():
    """D4(a) self-test — `sys.modules["core.voice"] = x` (a stub INSTALL, the 6 existing
    stub-install sites) is NOT a real-import force and is NOT flagged."""
    src = 'import sys\nsys.modules["core.voice"] = object()\n'
    assert _core_voice_force_imports(src) == []


# ══════════════════════════════════════════════════════════════════════════
# D4(b) — the blessed fixture keeps its guard + marker-consistency
# ══════════════════════════════════════════════════════════════════════════


def test_d4b_blessed_fixture_has_vacuity_guard():
    """D4(b) forward — the `real_voice` fixture in tests/conftest.py retains its
    `_load_ecapa_patched` assert. Drop it and the fixture could silently fall back to the
    stub (the Canary #3 vacuity); this tripwire forbids that."""
    src = _BLESSED_CONFTEST.read_text(encoding="utf-8")
    assert _real_voice_fixture_missing_guard(src) == [], (
        "tests/conftest.py `real_voice` fixture lost its `_load_ecapa_patched` vacuity guard "
        "— without it the fixture can silently yield the stub instead of the real module."
    )


def test_d4b_self_test_fixture_missing_guard_flagged():
    """D4(b) self-test — a synthetic real_voice fixture WITHOUT the guard is flagged."""
    src = (
        "import pytest\n"
        "@pytest.fixture\n"
        "def real_voice():\n"
        "    import importlib\n"
        "    real = importlib.import_module('core.voice')\n"
        "    yield real\n"
    )
    assert _real_voice_fixture_missing_guard(src) == ["real_voice"]


def test_d4b_self_test_fixture_with_guard_clean():
    """D4(b) self-test — a synthetic real_voice fixture WITH the guard is clean."""
    src = (
        "import pytest\n"
        "@pytest.fixture\n"
        "def real_voice():\n"
        "    import importlib\n"
        "    real = importlib.import_module('core.voice')\n"
        "    assert hasattr(real, '_load_ecapa_patched')\n"
        "    yield real\n"
    )
    assert _real_voice_fixture_missing_guard(src) == []


def test_d4b_real_voice_requesters_are_marked():
    """D4(b) forward — every test that requests the `real_voice` fixture is
    @pytest.mark.real_voice-marked (decorator or module pytestmark), so real-voice tests stay
    grep-discoverable + `-m real_voice`-selectable."""
    offenders: list[str] = []
    for f in _scanned_test_files():
        for name in _real_voice_requesters_missing_marker(f.read_text(encoding="utf-8")):
            offenders.append(f"{f.relative_to(_REPO_ROOT).as_posix()}::{name}")
    assert offenders == [], (
        f"test(s) requesting the `real_voice` fixture without an @pytest.mark.real_voice marker: "
        f"{offenders}. Mark them (decorator or module-level pytestmark) so they're discoverable."
    )


def test_d4b_self_test_unmarked_requester_flagged():
    """D4(b) self-test — an unmarked real_voice requester is flagged."""
    src = (
        "import pytest\n"
        "@pytest.mark.asyncio\n"
        "async def test_foo(real_voice):\n"
        "    pass\n"
    )
    assert _real_voice_requesters_missing_marker(src) == ["test_foo"]


def test_d4b_self_test_marked_requester_clean():
    """D4(b) self-test — a marked real_voice requester is clean (decorator form)."""
    src = (
        "import pytest\n"
        "@pytest.mark.real_voice\n"
        "def test_foo(real_voice):\n"
        "    pass\n"
    )
    assert _real_voice_requesters_missing_marker(src) == []


def test_d4b_self_test_module_pytestmark_marks_requester():
    """D4(b) self-test — a module-level `pytestmark = pytest.mark.real_voice` also satisfies
    the marker-consistency check (so single-purpose real-voice files need not decorate each)."""
    src = (
        "import pytest\n"
        "pytestmark = pytest.mark.real_voice\n"
        "def test_foo(real_voice):\n"
        "    pass\n"
    )
    assert _real_voice_requesters_missing_marker(src) == []


# ══════════════════════════════════════════════════════════════════════════
# D5 — the conftest stub's fail-LOUD falsy return (BEHAVIORAL, Q3)
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_d5_conftest_stub_embed_identify_fail_loud_falsy():
    """D5 (#126) — BEHAVIORAL lock on the conftest stub's fail-LOUD falsy returns.

    The vacuity guard's leverage is that the stub returns FALSY (embed → None,
    identify → (None, …)): a real-voice-behavior test run against the stub WITHOUT the fixture
    permanent-REDs, so it's caught on an honest run (this is what surfaced Canary #3). A stub
    mutated to return a truthy fake embedding would make such a test permanent-GREEN — silently
    passing against a mock, the worst regime D1-D4 can't see. Asserting BEHAVIORALLY (call the
    INSTALLED stub) per Q3: robust to an equivalent refactor + can't drift from a source-string
    of the stub. The coupling to the stub IS the point — the fail-loud-falsy property is itself
    a load-bearing invariant; forcing a conscious re-justification when the stub evolves is the
    SYNC_METHOD_ALLOWLIST "the lock forces the decision" discipline."""
    import sys
    stub = sys.modules.get("core.voice")
    assert stub is not None, (
        "conftest core.voice stub not installed — the autouse setup_pipeline_stubs() should run"
    )
    # Confirm we're testing the STUB, not the real module (the real one has _load_ecapa_patched).
    assert not hasattr(stub, "_load_ecapa_patched"), (
        "core.voice is the REAL module here, not the conftest stub — D5 must run against the "
        "stub (did a sibling real_voice test leak the real module past its finally-restore?)."
    )
    emb = await stub.embed(None, sample_rate=16000)
    assert not emb, (
        f"conftest stub `embed` must return a FALSY value (None) so a fixture-less real-voice "
        f"test permanent-REDs; got truthy {emb!r} — vacuity would become a silent GREEN."
    )
    res = await stub.identify(None)
    assert not res[0], (
        f"conftest stub `identify` must return a falsy-headed tuple ((None, …)); got head "
        f"{res[0]!r} — a truthy pid would let a stranger-vs-known test pass against the mock."
    )
