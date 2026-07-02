# Contributing to KaraOS

Thanks for your interest in contributing. This guide covers the practical
onboarding flow; project governance is in
[`GOVERNANCE.md`](GOVERNANCE.md), and community standards are in
[`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).

---

## Clone + install

KaraOS uses git-LFS for model weights and pinned git URLs for vendored
forks. The full restore flow is documented in [`SETUP.md`](SETUP.md). Short
version:

```bash
git clone https://github.com/HungryFingerss/KaraOS.git karaos
cd karaos
git lfs pull

python -m venv venv
source venv/Scripts/activate    # Windows; use `venv/bin/activate` on Linux/macOS

pip install -r requirements.txt
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128

cp .env.example .env
# fill in TOGETHER_API_KEY + TAVILY_API_KEY + HF_TOKEN
```

See `SETUP.md` for the full restore procedure, troubleshooting notes, and
post-install verification checklist.

---

## Run tests

The test suite is the load-bearing gate for every PR.

```bash
pytest                         # full suite
pytest -x                      # stop on first failure (debugging)
pytest tests/test_<name>.py    # single file
```

The cumulative passing count is tracked at the top of [`CLAUDE.md`](CLAUDE.md)
banner. Closure narratives MUST honor the locked
`Explicit-closure-honest-count-commitment` discipline — if your PR changes
the test count, the closure narrative documents the delta with a one-line
explanation.

Pre-existing infra-debt failures (e.g., pyannote/speechbrain Windows import
issues) are documented in the banner and are NOT contributor-introduced
regressions.

---

## Submit a PR

1. **Branch naming:** `<type>/<short-description>` (e.g. `fix/voice-routing-bug`,
   `spec/p1-a1-pipeline-decomposition`, `docs/setup-instructions-update`).
2. **Commit messages:** describe the substantive change, not the file
   movement. Link to the relevant issue or spec when applicable. Squash
   trivially-small commits before review.
3. **Reviewer assignment:** the BDFL adjudicates significant changes;
   `governance`-tagged PRs always route through BDFL. Subsystem-scoped
   changes may be reviewed by future Maintainers under Phase 2 governance
   (see `GOVERNANCE.md`).
4. **Tests pass.** `pytest` must be green on your branch before review.
   Document any new test-count delta in your PR description.
5. **PR description:** include "what changed + why" + the spec / issue
   reference + test outcome. For spec-track work, link to the relevant
   `tests/p0_*` / `tests/pre_p1_*` artifact.

---

## Strict-mode discipline (spec-track work)

KaraOS uses a strict-mode 3-artifact minimum cycle for non-trivial work:

1. **Phase 0 audit** — grep-verified findings reported BEFORE any test code
   is written. Skip this and rework cost exceeds the audit cost.
2. **Plan v1** — D-decisions surfaced explicitly. Architect/auditor sign-off
   locks them before code lands. Iterate to Plan v2 / Plan v3 absorbing
   auditor precision items.
3. **Closure** — deliberate-regression confirmations (`### Induction-
   surfaces-invariant-gaps` discipline), Path C grep-verify, closure
   narrative appended to `CLAUDE.md` banner.

Read the **Architectural Disciplines** section of `CLAUDE.md` for the
project's named patterns (Induction-surfaces-invariant-gaps,
Architect-reads-production-code-before-sign-off, Phase-0-catches-wrong-
premise, Twin-filename-pitfall-prevention, Phase-0-granular-decomposition-
enables-accurate-estimates, Grep-baseline-before-drafting,
Zero-precision-items-at-auditor-review, Canary-surfaces-real-gaps,
Pass-2-grep-auditor-verified-before-Plan-v1-approval, Pre-audit-quantifier-
precision-refined-by-grep, Resilience-track-arc-completion). New
contributors should expect to invoke these by name in PR discussions.

For trivial work (typo fixes, docstring polish), the strict-mode cycle is
not required — direct PR is fine.

---

## Project conventions

[`CLAUDE.md`](CLAUDE.md) is the source of truth for:

- Test count + breakdown
- Architecture overview + key config values
- Module roles (pipeline.py, core/*, brain agents)
- Completed sessions log + bug status
- Coding standards (no silent `except: pass`, all I/O through executor,
  all settings in `core/config.py`, etc.)
- Architectural Disciplines (named patterns above)
- Session protocol (start + end of every working session)

Read it before opening a non-trivial PR. The session-protocol section is
mandatory for spec-track work.

---

## License + copyright

KaraOS is licensed under the **Apache License 2.0** (see
[`LICENSE`](LICENSE) and [`NOTICE`](NOTICE)). Contributions are accepted
under this license; by submitting a PR you agree to license your
contribution under Apache 2.0.

New Python and YAML files must include the standard 2-line SPDX header
(applied uniformly via `python tools/add_spdx_headers.py`; the script is
idempotent so re-runs are safe). Vendored MIT-licensed code lives at
`core/_minifasnet/` and is EXCLUDED from the project-wide Apache 2.0
header per its upstream license terms.

---

## Questions

Open an issue tagged `question` or contact the BDFL at
[jagannivas.001@gmail.com](mailto:jagannivas.001@gmail.com). Code-of-conduct
concerns route to the same address per `CODE_OF_CONDUCT.md`.

---

**Last updated:** 2026-05-28 (Pre-P1 Bundle 2 — Governance landed).
