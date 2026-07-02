# docs/ — documentation tree

| Item | What it is |
|---|---|
| `architecture/` | **The full architecture reference** — 19 chapters (§1-§340) split from the original monolithic doc, with a CI-enforced section-number stability invariant (every §NN lives in exactly one chapter; duplicates fail the build). Start at `architecture/README.md` for the chapter index. The root `everything_about_system.md` is a thin redirect into this tree. |
| `embodied/` | `competitive_positioning.md` — the embodied-runtime positioning analysis (where KaraOS sits vs robot-specific SDKs and cloud agent stacks). |
| `silent-except-policy.md` | The swallow-discipline policy: every broad `except` must be annotated (`# RACE:`/`# CLEANUP:`/`# OPTIONAL:`) or log — the written half of the AST invariant in `tests/test_silent_except_invariant.py`. The title retains its historical name by a deliberate test-locked rule (history is not rewritten). |
| `karaos-showcase-legacy-README.md` | The README of the pre-merge public showcase repo, preserved verbatim when the codebase and showcase repos merged into one (2026-07-02) — the repo-level README superseded it; kept as the historical record. |

House rule: `docs/architecture/` refreshes on a consolidated cadence (not per-change); the per-cycle engineering record lives in `rule book/cycle-specs/` instead.
