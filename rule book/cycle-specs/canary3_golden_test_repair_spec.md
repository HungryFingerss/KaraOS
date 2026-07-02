# Spec — Canary #3 golden-test repair: GT1/GT1b must drive the REAL `core.voice`

**Status:** GREENLIT by auditor 2026-05-31 — ready for developer
**Author:** architect
**Date:** 2026-05-31
**Auditor rulings:** Q1=local · Q2=keep helper (called once, in-body calls removed) · Q3=defensive assert mandatory · Q4=function-scoped · Q5=file systemic follow-up (task #126, prefer `@pytest.mark.real_voice`). 3 non-blocking PIs absorbed below. No BLOCKING items.
**Depends on:** Canary #3 (Part A ECAPA subprocess patch + Part B rename gate) — CLOSED by developer, code verified correct in Layer-3.
**Production code changes:** NONE. This is a test-only repair.

---

## 0. One-paragraph summary

Layer-3 re-verification of Canary #3 found that the Part A fix is **correct** (proven three
independent ways — see §2) but the two golden tests meant to lock it (`GT1`,
`GT1b`) are **vacuous**: under pytest they import the conftest stub
(`tests/conftest.py:61` → `_voice_stub.embed = AsyncMock(return_value=None)`),
not the real `core.voice`, so `voice.embed(...)` returns `None` *by design* and the
tests can never go green on any host. They are a permanent false-RED. This spec makes
GT1/GT1b exercise the **real** `core.voice.embed` end-to-end so they become a working
regression lock — RED when Part A is reverted, GREEN when Part A is in place, **verified
on the CUDA dev box**. No production code is touched; the Part A/B fixes stay exactly as
shipped.

---

## 1. Problem statement (root cause, with evidence)

### 1.1 The fix is correct
Three runtime proofs on the CUDA dev box (`venv\Scripts\python.exe`, real speechbrain + CUDA):

| Path exercised | Call | Result |
|---|---|---|
| In-process worker | `hw.ecapa_embed_worker(bytes, shape, dtype, 16000)` | **OK — 768 bytes (192-dim)** |
| Real subprocess pool | `await hw.run_heavy("ecapa_embed", hw.ecapa_embed_worker, …)` | **OK — 768 bytes** |
| Real subprocess + parent CUDA/ECAPA pre-loaded (replicates GT1 skip-gate AND pipeline warmup) | same as above | **OK — 768 bytes** |

The patched loader (`core/voice.py::_load_ecapa_patched`, called by
`core/heavy_worker.py::_get_subprocess_ecapa`) produces valid embeddings through the real
subprocess dispatch. The real canary path is fixed.

### 1.2 The golden tests are vacuous
Direct probe under pytest (a one-test file under `tests/`):

```
VOICE __file__: <<STUB: no __file__>>
HAS _load_ecapa_patched: False
embed type: AsyncMock
embed result: None
```

`tests/conftest.py` installs a `core.voice` stub via the **autouse** fixture
`_reset_session_state_between_tests` → `setup_pipeline_stubs()`, which sets
`_voice_stub.embed = AsyncMock(return_value=None)` (line 61) whenever `core.voice` is not
already in `sys.modules`. GT1/GT1b import `core.voice` *inside their function bodies*
(`tests/test_canary3_ecapa_embed_and_rename_safety.py:62`,`:84`), so by the time they run,
the autouse fixture has already stubbed it. They assert `voice.embed(...) is not None`
against a mock hardcoded to return `None`. `test_canary3` sorts before `test_voice`, so
this happens in the full suite as well as in isolation — there is **no standard
`pytest tests/` ordering in which GT1/GT1b pass**.

### 1.3 The exact call paths (load-bearing for the design)
- **GT1** (`:57`): `import core.voice as voice` → `await voice.embed(audio, sample_rate=16000)`.
  Direct call on the imported module → gets the **stub**.
- **GT1b** (`:77`): `import pipeline as _pl` → `await _pl._accumulate_voice(pid, audio, db, face_verified=True)`.
  `_accumulate_voice` (`pipeline.py:2513`) calls `await voice_mod.embed(audio)`, where
  `voice_mod` is the **module-level alias** bound at `pipeline.py:380`
  (`from core import voice as voice_mod`). Because `pipeline` is imported while the stub is
  active, `pipeline.voice_mod` **is the stub object** — a *separate name binding* from
  `sys.modules["core.voice"]`.

  **Consequence:** force-importing real `core.voice` into `sys.modules` alone fixes GT1 but
  **NOT** GT1b. GT1b also requires `pipeline.voice_mod` to be re-pointed to the real module.

### 1.4 `_accumulate_voice` gate chain (confirms embed is GT1b's only blocker)
With GT1b's setup (`person_type="stranger"`, `bootstrap_credits=N_INITIAL_VOICE_BOOTSTRAP`,
`engagement_gate_passed=True`, 2.0 s audio, empty gallery):
- `_voice_accum_allowed` → `path="bootstrap"`, `allowed=True` (`pipeline.py:2459`).
- `voice_mod.identify(audio, {}, threshold)` → empty gallery → `(None, 0.0, …)`; only
  `v_pid`/`v_score` are consumed (`:2477`). `v_pid != person_id` → bootstrap branch at
  `:2488` sets `source="voice_face_verified"`; the Path-B weak-self-match skip at `:2491` is
  NOT taken.
- Duration gate `2.0 s ≥ MIN_VOICE_ACCUM_DURATION_SECS (1.5 s)` → passes (`:2506`).
- `emb = await voice_mod.embed(audio)` (`:2513`) → **the single embed-None blocker**.
  With a real module → real embedding → `db.add_voice_embedding` (`:2518`) → count grows by 1.

So re-pointing `pipeline.voice_mod` to the real module is **sufficient** for GT1b to go green.

---

## 2. Goal / success criterion

GT1 and GT1b exercise the **real** `core.voice.embed` end-to-end (parent-side resolution
hits the real module; the embed dispatches to the real `ecapa_embed` subprocess, which
always re-imports real `core.voice` regardless of parent `sys.modules`). The success
criterion is a genuine RED→GREEN demonstrated **on the CUDA dev box**:

- **Part A in place** → GT1 returns a 192-dim embedding, GT1b grows
  `voice_embedding_count` by 1. **GREEN.**
- **Part A reverted** (un-patched `_get_subprocess_ecapa`) → subprocess load fails →
  `voice.embed` returns None → both **RED.**

A GPU-less skip is **not** acceptable evidence (this is exactly the "vacuous skip" the
auditor warned about, and the blindness that hid the original bug).

---

## 3. Design

### D1 — `real_voice` pytest fixture (LOCAL to `tests/test_canary3_ecapa_embed_and_rename_safety.py` — Q1 RULING)

A function-scoped (Q4 RULING) fixture that (a) skips on non-CUDA/no-speechbrain hosts via the
named helper (Q2 RULING), (b) swaps the conftest stub for the real `core.voice`, (c) re-points
`pipeline.voice_mod`, (d) restores both on teardown **even if setup raises** (PI-1 hardening:
capture pre-state BEFORE any mutation; do all mutation + the defensive assert + the yield
INSIDE a `try`; restore in `finally` — so a defensive-assert failure during setup can't leak
the popped stub). Reference shape:

    @pytest.fixture
    def real_voice():
        _require_real_ecapa_or_skip()                 # Q2: named helper, called ONCE here
        import sys, importlib, pipeline
        _stub    = sys.modules.get("core.voice")      # capture BEFORE any mutation
        _orig_vm = getattr(pipeline, "voice_mod", None)
        try:
            sys.modules.pop("core.voice", None)
            real = importlib.import_module("core.voice")
            assert hasattr(real, "_load_ecapa_patched"), \
                "real core.voice not loaded — stub still active"   # Q3: mandatory, fail-loud
            pipeline.voice_mod = real                  # §1.3: re-point the alias (load-bearing)
            yield real
        finally:                                       # PI-1: ALWAYS restores, even on setup raise
            pipeline.voice_mod = _orig_vm
            if _stub is not None:
                sys.modules["core.voice"] = _stub
            else:
                sys.modules.pop("core.voice", None)

Load-bearing details:
- **Import `pipeline` before popping the stub** so `_orig_vm` captures the *current* (stub)
  binding → teardown restores exactly the pre-fixture state (zero leak into later tests).
- **The defensive assert (Q3, mandatory)** is the single most important line: it fails loud if
  the swap ever silently breaks (helper rename, stub-order change, broken pop/import), so the
  test can never silently regress back into testing the mock. It is the in-fixture analogue of
  the A2-guard's fail-loud discipline. `_load_ecapa_patched` is a valid discriminator — the
  conftest stub (`tests/conftest.py:40-63`) does not define it; no `isinstance(...AsyncMock)`
  over-spec needed.
- **PI-1 (auditor):** the `try/finally` wraps mutation + assert + yield so even an
  assert-during-setup restores `sys.modules`/`voice_mod`. Without it, pytest skips a
  yield-fixture's teardown when setup raises → the popped stub leaks as the real module
  (low-severity but avoidable).

### D2 — GT1 consumes the fixture
`async def test_gt1_ecapa_subprocess_returns_embedding(real_voice):`
Body: build 2.0 s audio; `emb = await real_voice.embed(audio, sample_rate=16000)`; assert
`emb is not None`; assert `emb.shape == (192,)`. Remove the in-body
`import core.voice as voice` and the direct `_require_real_ecapa_or_skip()` call (now in the
fixture).

### D3 — GT1b consumes the fixture
`async def test_gt1b_accumulate_voice_grows_gallery(real_voice, tmp_path):`
Body unchanged except: drop the `_require_real_ecapa_or_skip()` call. `pipeline.voice_mod`
is already real (fixture re-pointed it) so `_pl._accumulate_voice(...)` reaches the real
embed → count grows by 1. Keep the existing DB seed + session setup + the
`db._conn.close()` / `_close_session` teardown in the `finally`.

### D4 — `_require_real_ecapa_or_skip` (Q2 RULING — KEEP as a thin helper)
Keep the named skip-gate helper; the `real_voice` fixture calls it ONCE (D1). It stays a
greppable, isolated-testable skip contract and is reusable by the Q5 marker later.
**Mandatory cleanup:** remove the inline `_require_real_ecapa_or_skip()` calls from GT1's body
(`:60`) and GT1b's body (`:81`) — the fixture now owns the gate, so leaving them runs it twice
(harmless but redundant/confusing). Net: one named helper, called once by the fixture, zero
in-body calls.

### D5 — Scope of the conftest stub: UNCHANGED
The autouse `core.voice` / `core.audio` stub stays. It is load-bearing for the ~30 other
test files that import pipeline on Windows without the torchaudio DLL crash. We are NOT
removing it; we are making GT1/GT1b *opt out* of it locally. This keeps the blast radius to
GT1/GT1b only.

---

## 4. RED-proof (developer MUST run on the CUDA dev box)

1. With Part A in place + this repair: run GT1/GT1b → **GREEN** (192-dim; count +1).
2. Temporarily revert Part A only — restore the un-patched `_get_subprocess_ecapa`
   (the version that called `EncoderClassifier.from_hparams(...)` WITHOUT routing through
   `_load_ecapa_patched`): run GT1/GT1b → **RED** (`voice.embed returned None`).
3. Restore Part A → GREEN again.

Capture the three states (GREEN / RED / GREEN) in the developer handoff as the evidence the
test now genuinely exercises the patched loader. Step 2 RED on the CUDA box is the proof the
test is no longer vacuous. Do NOT substitute a GPU-less skip.

**Strengthening (auditor).** Reverting Part A (a bare `from_hparams` in
`_get_subprocess_ecapa`) ALSO makes the always-CI structural guard
`test_a2_guard_from_hparams_only_in_shared_patch_helper` go RED — a `from_hparams` site
outside `_load_ecapa_patched`. So the Part-A revert produces **two independent RED signals**:
GT1 (behavioral, CUDA-gated — proves the embedding returns) AND the A2-guard (structural,
every-PR — proves the routing). **Record BOTH.** GT1 proves the value; the A2-guard is the
half that protects the repo on every future PR where no GPU runs GT1.

**Framing (record).** Golden-test-first has a blind spot — a permanently false-RED test (a
mock hardcoded to fail) is indistinguishable from a genuine reproduction unless you verify the
RED fails *for the right reason*. "Green must mean the product works" generalizes to **"RED
must fail for the production reason, not the mock."** Step 2 is what verifies it.

---

## 5. Adversarial review (pre-empting auditor precision items)

- **Fixture ordering.** pytest sets up autouse function-scoped fixtures
  (`_reset_session_state_between_tests`) before explicit ones requested by the test
  (`real_voice`) within the same scope. So the autouse stub install happens first, then
  `real_voice` overrides it. Correct by the standard resolution rule. (If the auditor wants
  belt-and-braces, the D1.4 defensive assert fails loudly if the override didn't take.)
- **Teardown leakage.** The fixture restores BOTH `sys.modules["core.voice"]` and
  `pipeline.voice_mod` to their captured pre-fixture values. It is a `yield` fixture, so
  teardown runs even on test failure. Importing pipeline *before* popping the stub (D1.2)
  guarantees `_orig_vm` is the stub, so post-test `pipeline.voice_mod` is the stub again →
  zero leak into later tests.
- **Real `identify` on an empty gallery.** GT1b pops the gallery first; real
  `voice_mod.identify(audio, {}, threshold)` returns `(None, 0.0, …)` without crashing
  (empty gallery → no match). Only `v_pid`/`v_score` are consumed at `:2477`; the bootstrap
  branch at `:2488` proceeds. Confirmed against the live source.
- **The subprocess is always real.** `hw.run_heavy("ecapa_embed", …)` spawns a child that
  re-imports real `core.voice` regardless of parent `sys.modules`. The fixture only fixes
  the **parent-side** resolution (which object GT1/`_accumulate_voice` invoke). The
  embedding itself is produced by the real subprocess — proven by the §1.1 runtime tests.
- **Blast radius.** Grep of `tests/` returns **41** files referencing `voice_mod`/`core.voice`
  (includes `.md` specs + fixtures; the count is decorative — PI-3 — the argument holds at any
  count). All are standard stub-consumers or specs. A function-scoped fixture that restores in
  teardown affects only GT1/GT1b. `test_voice.py` (real voice) and
  `test_p0_r6_y_ecapa_worker.py` (structural) are present in the list and untouched.
- **PI-2 (GT1b setup soundness — developer "look once").** GT1b's pre-existing setup calls
  BOTH `_pl._open_session(...)` (`:95`) and `await _pl._session_store.open_session(...)`
  (`:97`). The double-open is out of this repair's scope, but when GT1b goes GREEN on the dev
  box, confirm the `+1` is a genuinely-once-opened bootstrap session (`path=bootstrap`,
  `source=voice_face_verified` in the log), not an artifact of the double-open masking a setup
  quirk. A look-once check, not a gate.
- **GT2 / GT2-companion unaffected.** They mock the DB and test
  `_is_enrollment_mishear_candidate` directly; they don't call `voice.embed`, take no
  fixture, and stay green. Part B's lock is intact.
- **A2-guard / Q2-unit unaffected.** Pure AST inverse-checks on source; no voice import.

---

## 6. Q-block — RULINGS (auditor 2026-05-31)

- **Q1 — fixture location: LOCAL** to `test_canary3_*.py`. Needed by exactly two tests in this
  file; hosting in `tests/conftest.py` would expose a stub-popping fixture to every `tests/`
  test (a loaded gun if requested by name). Generalizing belongs to Q5, not a default-now.
- **Q2 — KEEP `_require_real_ecapa_or_skip` as a thin helper** the fixture calls once.
  Preserves a greppable, isolated-testable skip contract + reusable by the Q5 marker later.
  **Mandatory:** remove the inline calls from GT1 (`:60`) + GT1b (`:81`) — fixture owns the
  gate now (D4).
- **Q3 — defensive assert: MANDATORY.** `assert hasattr(real, "_load_ecapa_patched")` — the
  single most important line; the in-fixture analogue of the A2-guard's fail-loud discipline.
  Without it a future refactor could silently re-introduce the vacuity. Valid discriminator
  (the stub lacks the symbol); no `isinstance(...AsyncMock)` over-spec needed.
- **Q4 — function-scoped.** Isolation > the ~20 s module-scope saving on two CUDA-gated tests;
  also avoids a module-scope window where the real module lingers in `sys.modules` across the
  autouse guard between GT1 and GT1b.
- **Q5 — FILE the systemic follow-up** (task #126, separate cycle, out of scope here per §9).
  The autouse stub shadows `core.voice`/`core.audio` for every `tests/` test, so any future
  "real pipeline" golden test silently tests the mock unless it opts out. **Prefer a
  `@pytest.mark.real_voice` marker the autouse fixture respects** (declarative, greppable,
  can't-be-forgotten) over per-test asserts. Touches the autouse contract + every future
  golden test — larger work, deliberately not folded into this cycle.

---

## 7. Files touched

- `tests/test_canary3_ecapa_embed_and_rename_safety.py` — add `real_voice` fixture; rewire
  GT1 + GT1b to consume it; adjust/remove `_require_real_ecapa_or_skip` per Q2.
- **No production code.** Part A (`core/voice.py`, `core/heavy_worker.py`) and Part B
  (`pipeline.py`, `core/config.py`) stay exactly as shipped.
- **No conftest change** (unless Q1 chooses to host the fixture there).

## 8. Test-count impact

Net **0 new tests**. GT1/GT1b already exist; they go from vacuous (false-RED) to real
(RED→GREEN provable on the CUDA box). All other anchors (GT2, GT2-companion, Q2-unit,
A2-guard, the P0.R6.Y anchor) are unchanged.

## 9. Out of scope

- Removing or narrowing the conftest `core.voice`/`core.audio` stub (other tests need it).
- The systemic golden-test-vacuity guard (Q5) — flagged for a separate follow-up if the
  auditor agrees.
- Any production behavior change. The fix is correct; this repair only makes the lock real.
