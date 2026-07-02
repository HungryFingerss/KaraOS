# tests/ — the actual test suite

**189 test files in this folder** (plus 7 legacy `test_*.py` at repo root), **4,237 passing / 0 failed** as of 2026-07-03 (4,259 collected: +12 skipped, +7 xfailed, +3 xpassed). `asyncio_mode=auto`.

## Run it
```bash
# the standard full run (from repo root — collects tests/ + the root test files)
python -m pytest --ignore=tests/test_brain_json_parser_hypothesis.py -q

# the hypothesis property-based file (36 tests) needs `pip install hypothesis`
python -m pytest tests/test_brain_json_parser_hypothesis.py -q

# fast CI subset (what fast.yml runs)
python -m pytest -m "not slow and not network and not models" -q
```

## What's in here (the layers)
- **Behavioral / golden tests** — drive the REAL pipeline, mocking only hardware. Goldens live in `goldens/` (e.g. the byte-exact composed system prompt) and `golden/sb41_full/` (3 full prompt-block renders). The project rule: a capability is not done until a behavioral test proves it against the real code path, RED-first for the production reason.
- **Structural invariants (~25 files)** — AST-enforced disciplines that fail CI on violation: `test_silent_except_invariant.py`, `test_no_walltime_deadline_math.py`, `test_layering_invariants.py`, `test_secrets_invariants.py`, `test_no_production_assert.py`, `test_spdx_headers_invariant.py`, the store/schema/paired-write invariant families, `test_real_voice_convention.py`, and the registry-coverage tripwires. These are the rule book made executable.
- **Contract tests** — the reconciler's 21 routing contracts + 27 per-rule + veto negatives (`test_p10_reconciler_contract.py`, `test_reconciler.py`), locked against `reconciler_golden.py` (51 golden cases, count+uniqueness self-checked at import).
- **Eval benches (manual/cron, not collected by pytest)** — `eval_intent_bench.py` (the 149-row `golden_intent.jsonl` corpus vs the live classifier; persists runs to `eval_bench_runs/`), `eval_weekly.py` (drift report + `--alert`), `golden_set_drift.py` (quarterly label review), `harvest_golden.py` (mines session logs into new golden rows), `smoke_privacy_classifier.py`.
- **Fixtures & helpers** — `conftest.py` (autouse store resets + hardware stubs), `_pipeline_helpers.py`, `fixtures/` (event-log scenario builders + a canary transcript), `canary_week_2026-05-26.md` (a live-canary runbook a test reads — kept here for that reason).

## Conventions with teeth
- **No test touches real production paths** — destructive ops monkeypatch every path constant to `tmp_path`. This rule exists because a test once silently wiped real enrolled faces on every pytest run.
- **Markers** (registered in `pytest.ini`): `slow`, `network`, `models`, `privacy_critical` (runs un-skippable as a separate CI step — a skipped privacy test fails the build), `real_voice` (forces the real `core.voice` past the autouse stub, with a vacuity guard).
- **Deliberate-regression proven** — the invariant tests were each verified by breaking the thing they guard and watching them fire for the production reason (the RED ledgers live in `rule book/cycle-specs/`).
