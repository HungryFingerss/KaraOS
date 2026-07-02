# Developer — Testing Disciplines

## The prime directive: golden-test-first
A capability is not done until an automated behavioral test drives the REAL pipeline, mocking ONLY hardware (Jagan 2026-05-30). Green CI must mean "the product works," not "the code is shaped right." The user must never be the regression detector.
- **The RED must fail for the production reason** — a golden test proven RED against the real broken path, then GREEN on the fix. A permanently-false-RED is indistinguishable from a reproduction (the Canary-#3 vacuous GT1: it tested a mock hardcoded to None and could never pass).
- **The GREEN must pass for the production reason** (SB.7's extension) — pair proxy-free mechanism assertions with vacuity guards (count guards, interval-overlap over wall-clock). A fixture that rots crashes early and makes a weak assertion pass on the crash-fast path — for ~20 sessions, in one banked case.
- **Mechanism over proxy**: assert WHAT the code does (interval overlap = concurrency; byte-identity = preservation; the pinned action = the veto), not a wall-clock or a keyword that correlates with it under today's load.

## Test isolation (absolute)
- **No test touches real production paths** — destructive ops (`wipe_all`, migrations, DB inits) monkeypatch the path constants to `tmp_path`. A comment saying "can't redirect" is a bug to fix, not a caveat. Provenance: the Session-122 test that silently deleted real enrolled faces on every pytest run for days. *Enforced by review + the tmp-path patterns in every A3-class battery.*
- Stores/state reset between tests (the autouse fixture loops); test DBs closed before tmp cleanup; per-test isolation verified when ordering-determinism surfaces latent leaks.

## Structural invariants (the CI-enforced discipline layer)
- **Prefer AST forward-property checks over source-substring checks** — docstrings/comments false-satisfy substring ordering checks (3+ banked instances); AST shapes don't. Where substrings are unavoidable, normalize adjacent string literals and require call-shapes, not bare names.
- **Every enumerated set ships its inverse check**; every allowlist entry carries rationale; allowlists are re-derived from the detector's fresh scan on drift, and (post-SB.8) content-keyed allowlists beat line-keyed ones — a stale line-key can silently bless the WRONG site (STALE-KEY-COLLISION: under-reporting, the dangerous direction).
- **Deliberate-regression on every invariant you ship**: break it → your test fires with the right message → restore → suite green. Report the (a)/(b)/(c) list with outcomes. A config switch's regression check proves BOTH the object is gone AND the behavior is gone (board §8.2).
- **Locks are two-directional where the failure is** (SB.7 A2 tri-directional; SB.9's inverse tripwire): adding-the-wrong-thing must fail AND adding-the-right-thing must move all coupled counters together — one-but-not-the-other FAILS.

## Golden/baseline discipline
- Goldens are captured BEFORE the cut lands (the SB.2 T1 / SB.8 pattern) — the before-state is the reference, extracted verbatim, byte-compared.
- Byte-identity is the contract for preservation claims; **set-equality/behavioral-equivalence where order is legitimately free** (the SB.9 hygiene-regex acceptance — byte-identity there would be a false-failure trap).
- Baselines/goldens regenerate only through the same code path that consumes them (`--write-baseline`), and re-baselining is a human-reviewed commit, never CI-auto.
- Deterministic by construction: fixed seeds, no `Date.now()`-class nondeterminism in fixtures, determinism proven across fresh processes before pinning (the n4b 3-process rule).

## Conventions with teeth
- `@pytest.mark.real_voice` + the shared fixture for anything exercising real `core.voice` (the #126 convention: the conftest stub returns falsy BY DESIGN so vacuous tests fail loud). *Enforced: `tests/test_real_voice_convention.py`.*
- Markers registered in pytest.ini; privacy-critical tests run un-skippable in CI (`tests/test_p0_s7_privacy_critical.py` + the fast.yml/slow.yml split).
- Platform/env-gated tests use `importorskip`/capability probes, never bare failure on a box without the hardware.
