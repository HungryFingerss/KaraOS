# Follow-up #126 — systemic `@pytest.mark.real_voice` golden-test vacuity guard

**Status:** LOCKED — auditor GREENLIGHT 2026-05-31. Ready for the developer.
**Lineage:** post-canary follow-up #4 of 4 — the LAST (order: #129 ✓ → #123 ✓ → #128 ✓ → **#126**).
Generalizes the Canary #3 lesson into a project-wide convention: a real-voice golden test must
provably exercise the REAL `core.voice` module, never the conftest stub. **Preventive** — the only
current real-voice-behavior test (GT1/GT1b) is already protected by the #125 local fixture; #126
turns that one-off into a marker + shared fixture + a CI tripwire so a FUTURE golden test can't
reinvent the unguarded force-import (the mistake that hid the Canary #3 embed-None bug for a week).
This is the Q5 follow-up the auditor endorsed in the original Canary #3 verdict ("prefer the
`@pytest.mark.real_voice` marker — declarative, greppable, can't-be-forgotten").

**Auditor disposition (folded in):** GREENLIGHT D1 + D2 + D3 + D4 + **D5 (included)**, no BLOCKING
items. Surface grep-verified (1 force-import site, 0 hidden real-voice-behavior tests, no marker
today, stub fail-loud-falsy). Q1 = `tests/conftest.py`, **D4(a) excludes ONLY that file (not the
`conftest.py` basename — there are TWO autouse conftests, root + tests/; an unguarded force-import
in the ROOT conftest must NOT evade the tripwire)**. Q2 = keep `_require_real_ecapa_or_skip`
ECAPA-specific, no rename, **document the fixture's ECAPA scope in its docstring**. Q3 = include D5,
**prefer a BEHAVIORAL assertion (call the installed stub's embed/identify, assert falsy) over a
brittle exact-construction AST match**. Q4 = D4(a) **exact-string `== "core.voice"` match MANDATORY**
(the `importlib.import_module("core.voice_channel")` at `test_voice_channel.py:74` is a real
false-positive a loose check would hit) + the mechanism caveat. PI = **D4's detectors via ONE shared
helper** (the #123 PI-1 / #128 D1 self-test discipline — the self-tests must validate the same
detector that scans production).

---

## 0. Phase 0 — the audit (grep + read-verified; auditor-reconfirmed)

**The Canary #3 vacuity class.** The autouse `_reset_pipeline_state_between_tests`
(`tests/conftest.py:214`) calls `setup_pipeline_stubs()`, installing a `core.voice` stub with
`embed = AsyncMock(return_value=None)` (`:61`) + `identify = AsyncMock(return_value=(None, 0.0, True))`
(`:57`) into `sys.modules` (guarded by `if "core.voice" not in sys.modules`). A golden test that
imports `core.voice` and asserts real behavior against THAT stub is **vacuous** (tests a mock
hardcoded to None — permanent false-RED). GT1/GT1b were exactly this; the developer's "validated
GREEN" was unsubstantiated until Layer-3.

**The #125 fix (local).** `tests/test_canary3_ecapa_embed_and_rename_safety.py` has a `real_voice`
fixture (`:53-89`): `_require_real_ecapa_or_skip()` (`:39`, speechbrain + CUDA skip gate) → captures
the stub + `pipeline.voice_mod` → `sys.modules.pop("core.voice")` + `importlib.import_module("core.voice")`
→ **the vacuity guard** `assert hasattr(real, "_load_ecapa_patched")` (`:80`) → re-points
`pipeline.voice_mod = real` (load-bearing — GT1b reaches embed via the `voice_mod` alias, a SEPARATE
binding) → try/finally restores both (PI-1).

**The systemic gap (grep-verified).** Good fixture, LOCAL to one file, no convention. (1) `pytest.ini`
4 markers, NO `real_voice`; (2) fixture + skip gate only in the canary3 file; (3) nothing detects
the vacuity anti-pattern. The real-import force `importlib.import_module("core.voice")` appears at
EXACTLY 1 site (`test_canary3:79`) — auditor-confirmed; the `test_voice_channel.py:74` match is
`"core.voice_channel"` (a DIFFERENT module, Q4's false-positive driver). The 6 stub-INSTALL sites
(`test_dispute_auto_clear:32`, `test_multispeaker_integration:19/52`, `test_user_text_gate_*`) are
`sys.modules["core.voice"] = _voice_stub` assignments (stub installs, not real-imports — correctly
outside D4(a) scope). `test_voice.py:33` is a retirement-sentinel surface check (symbol-absent, true
for stub AND real — not a real-voice-behavior assertion; CLAUDE.md's "test_voice.py exercises the
real modules" is STALE post-P0.R6.Y/Z). So the surface to guard is small + clean.

---

## 1. Decisions

### D1 — register `@pytest.mark.real_voice` (pytest.ini)
Add the marker, docstring naming the contract: "test exercises the REAL `core.voice` module past the
conftest stub via the shared `real_voice` fixture; skips cleanly when the real (ECAPA) model isn't
available; the fixture's `_load_ecapa_patched` assert is the vacuity guard." Makes real-voice tests
grep-discoverable + `-m real_voice` selectable.

### D2 — extract the shared `real_voice` fixture + skip gate to `tests/conftest.py`
Move `_require_real_ecapa_or_skip` + the `real_voice` fixture verbatim into `tests/conftest.py`
(beside `setup_pipeline_stubs` + the autouse — the stub's home; a `tests/conftest.py` fixture covers
all of `tests/`). Keep ALL load-bearing properties: the `_load_ecapa_patched` vacuity guard
(MANDATORY), the `pipeline.voice_mod` re-point, the try/finally restore (PI-1). **Q2 — document in
the fixture docstring that the skip gate is ECAPA-specific** (speechbrain + CUDA): the fixture name
is generic (`real_voice`) but its availability gate is ECAPA, so a future pyannote/whisper real-voice
test author must add their own model-availability gate, not assume `real_voice` covers it.

### D3 — migrate GT1/GT1b to the shared fixture + marker
`test_canary3_ecapa_embed_and_rename_safety.py`: delete the local `real_voice` + `_require_real_ecapa_or_skip`
(now in conftest), mark GT1/GT1b `@pytest.mark.real_voice`, keep them requesting the shared
`real_voice` fixture. **Closure-gate clause (auditor): the migration must PRESERVE the #125 RED→GREEN
proof** — re-confirm POST-migration that GT1/GT1b still fail-RED on a Part-A revert (neutralize
`_get_subprocess_ecapa`'s shared-helper patch) on the CUDA box. Moving the fixture must not regress
the very property that made #125 non-vacuous.

### D4 — the systemic tripwires (the core preventive value, → new `tests/test_real_voice_convention.py`)
**PI (mandatory): each detector is ONE shared source-string helper** that BOTH the forward test (real
`tests/` files) AND the self-tests (synthetic sources) route through — the #123 PI-1 / #128 D1
discipline, so the self-tests validate the SAME detector that scans production (no vacuity, no
divergence; #126's own detector must not be vacuous about a vacuity guard).

- **(a) force-import only in the blessed fixture.** Shared helper `_core_voice_force_imports(source)
  -> list[int]` returns line numbers of `ast.Call` to `importlib.import_module(...)` whose single
  string arg is **exactly `"core.voice"`** (`== "core.voice"`, NOT prefix/`in`/`startswith` — Q4:
  `"core.voice_channel"` is a legitimate different-module import a loose check would false-flag).
  Forward test: scan every `tests/**/*.py` EXCEPT the specific blessed file `tests/conftest.py`
  (Q1 — exclude that exact path, NOT the `conftest.py` basename; the root conftest is in scope so an
  unguarded force-import there is still caught) → assert ZERO force-imports. Self-tests route through
  the same helper: synthetic source WITH `importlib.import_module("core.voice")` → flagged;
  `importlib.import_module("core.voice_channel")` → NOT flagged; stub-install `sys.modules["core.voice"] = x`
  → NOT flagged.
- **(b) the blessed fixture keeps its guard + marker-consistency.** Shared helper checks
  `tests/conftest.py`'s `real_voice` fixture body contains the `_load_ecapa_patched` assert (forward +
  self-test [a synthetic fixture missing it → flagged]). Plus a marker-consistency check: every test
  function that requests the `real_voice` fixture (param) is `@pytest.mark.real_voice`-marked (module
  `pytestmark` or decorator) — discoverability.

### D5 — lock the conftest stub's fail-LOUD falsy return (BEHAVIORAL — Q3)
The vacuity guard's leverage is that the stub returns FALSY (`embed → None`, `identify → (None, …)`):
a real-voice-behavior test run against the stub WITHOUT the fixture (so D4 is blind) permanent-REDs →
caught on an honest run (this is what surfaced Canary #3). A stub mutated to return a truthy fake
embedding would make such a test permanent-GREEN — silently passing against a mock, the worst regime
D1-D4 can't see. D5 keeps vacuity catchable. **Q3 — assert BEHAVIORALLY, not via brittle AST:** in a
clean stub context, call the installed `core.voice` stub's `embed` (await it) → assert the result is
falsy; call `identify` → assert the returned tuple is falsy-headed. Behavioral (a) is robust to a
semantically-equivalent refactor (`AsyncMock(return_value=None)` → `async def embed(...): return None`)
and (b) can't drift from the real stub (it tests the INSTALLED stub, not a source-string of it). The
coupling-to-the-stub is the POINT — the fail-loud-falsy property is itself a load-bearing invariant;
forcing a conscious re-justification when the stub evolves is the SYNC_METHOD_ALLOWLIST "the lock
forces the decision" discipline.

---

## 2. Scoping caveats (document in-code, #123 D2b precedent)
- **D4(a) mechanism scope (Q4):** the detector matches `importlib.import_module("core.voice")` exact-
  string. A future test real-importing via `__import__("core.voice")` OR `sys.modules.pop("core.voice")`
  followed by a PLAIN `import core.voice` statement would be missed (the pop-then-plain-import compound
  is hard to AST-detect robustly). Scope to the `importlib.import_module` shape the project uses; note
  the assumption rather than chasing every mechanism. (The blessed fixture's teardown does
  `sys.modules.pop` + `sys.modules["core.voice"] = _stub` — a RESTORE, not a pop-then-real-import, so
  it isn't a force-import; the `tests/conftest.py` exclusion covers it regardless.)
- **D5 is behavioral, not structural** (per Q3) — so it needs no AsyncMock-shape caveat; it tests the
  installed stub's runtime falsy-return, robust to equivalent refactors.

## 3. Open questions — RESOLVED (auditor 2026-05-31)
- **Q1 — RESOLVED: `tests/conftest.py`**; D4(a) excludes ONLY that exact file (the root conftest stays
  in scope so an unguarded force-import there is caught — exclude the path, not the basename).
- **Q2 — RESOLVED: keep `_require_real_ecapa_or_skip` ECAPA-specific**, no rename; document the
  fixture's ECAPA-scoped availability gate in its docstring.
- **Q3 — RESOLVED: include D5, behavioral assertion** (call the installed stub, assert falsy) over a
  brittle exact-construction AST match.
- **Q4 — RESOLVED: exact-string `== "core.voice"`** match MANDATORY (the `core.voice_channel`
  false-positive is real) + the mechanism caveat.

## 4. Estimate
~6-8 logical anchors: D1 marker + D2 fixture+guard in conftest + D3 GT1/GT1b marked+shared + D4(a)
force-import tripwire (forward + self-tests via the shared helper) + D4(b) guard-present + marker-
consistency + D5 behavioral stub-fail-loud lock. Actual lands at closure (detector run authoritative).

## 5. Non-goals
- Does NOT change any production `core/` code — test-infrastructure + convention only.
- Does NOT alter GT1/GT1b's behavior (same fixture, guard, skip — relocated + marked; #125 RED→GREEN
  contract preserved per D3).
- Does NOT retro-migrate the stub-INSTALL tests (not real-voice-behavior tests; not vacuity-prone).
- Does NOT add CI marker-selection wiring (a `real_voice` CI step is a separate ops change; the
  marker registration suffices for grep + `-m real_voice`).

## 6. Closure gate (auditor-affirmed)
- D1 marker registered; `--strict-markers` clean.
- D2 fixture + skip gate in `tests/conftest.py` with the `_load_ecapa_patched` guard + PI-1 restore +
  the ECAPA-scope docstring note.
- D3 GT1/GT1b green via the shared fixture, `@pytest.mark.real_voice`-marked; **the #125 RED→GREEN-on-
  CUDA contract re-confirmed POST-migration** (Part-A revert → GT1/GT1b RED).
- D4 tripwires green (no ad-hoc real-import; guard present; marker-consistent), detectors via the
  shared helper (self-tests route through it).
- D5 behavioral stub-fail-loud lock green.
- **Behavioral-RED ×3:** (a) inject an ad-hoc `importlib.import_module("core.voice")` into a `tests/`
  file (not conftest) → D4(a) FAILS naming it → revert; (b) drop the `_load_ecapa_patched` assert from
  the conftest fixture → D4(b) FAILS → revert; (c) flip the conftest stub `embed` to a truthy return →
  D5 FAILS → revert. Net-zero.
- Full suite green + Layer-3 (shared fixture genuinely shared, guard structurally locked, detectors
  non-vacuous via the behavioral-REDs + shared-helper self-tests, Q4 caveat documented, the
  arc-completion milestone banked at closure).
