# KaraOS Governance

This document describes how the KaraOS project is governed today and how
governance will evolve as the contributor base grows.

---

## Philosophy

KaraOS is the Layer D cognitive runtime middleware for embodied AI — the layer
above motor control and below natural-language orchestration. The runtime
targets a 3-5 year market-defining horizon as the standard middleware for any
embodied AI agent.

Governance reflects the project's open-source-builder-first stance:
correctness, transparency, and contributor onboarding are the load-bearing
values. Decisions are documented in-repo (specs under `tests/p0_*` /
`tests/pre_p1_*` plus the strict-mode discipline locked in `CLAUDE.md`) so a
new contributor can audit the trail from first principles.

---

## Current phase — Phase 1: BDFL

**Benevolent Dictator For Life (BDFL):** [Jagannivas](mailto:jagannivas.001@gmail.com).

Jagannivas is the sole adjudicator for project direction, scope, governance,
and release readiness. All non-trivial scope changes route through the BDFL.

This is the appropriate governance model for the current contributor scale
(single-maintainer + AI-assisted development). It will evolve as the
contributor base grows; see "Future evolution" below.

---

## Decision-making process

1. **Issue first.** All non-trivial proposals (new features, scope changes,
   architectural shifts, P0/P1 specs) start as a GitHub issue tagged `rfc`
   describing the problem, proposed approach, alternatives considered, and any
   relevant trade-offs.
2. **Public discussion.** The issue is open for discussion before any PR
   lands. Comments document the conversation so the trail is preserved.
3. **BDFL adjudication.** Jagannivas adjudicates the proposal. For
   spec-track work (P0.* / Pre-P1.* / P1.*), the strict-mode 3-artifact
   minimum cycle (Phase 0 audit → Plan v1 → closure) is the locked discipline;
   complex specs may iterate through Plan v2 / Plan v3 absorbing precision
   items per the locked cycle pattern.
4. **PR lands.** Once approved, a PR implements the spec. Closure narrative
   appended to `CLAUDE.md` banner per the locked discipline.

Minor changes (typo fixes, docstring polish, dependency-pin bumps without
behavioral effect) can land via direct PR without the RFC step.

---

## Contributor expectations

Contributors are expected to:

- **Read `CLAUDE.md` first.** It is the source of truth for project
  conventions, named architectural disciplines (Induction-surfaces-invariant-
  gaps, Architect-reads-production-code-before-sign-off, etc.), coding
  standards, and the session protocol.
- **Honor strict-mode discipline** for spec-track work: Phase 0 audit (grep-
  verified findings) → Plan v1 → closure with deliberate-regression
  confirmations. No `while I'm here` content edits during mechanical-extraction
  work.
- **Run tests.** `pytest` must pass before any PR is opened (modulo
  pre-existing infra debt documented in the banner).
- **Document closures.** Every spec closure appends a narrative entry to the
  `CLAUDE.md` banner with doctrine count bumps and regression confirmations.
- **Respect SPDX headers.** All new Python and YAML files require the
  `SPDX-License-Identifier: Apache-2.0` + `SPDX-FileCopyrightText` headers.
  Use `python tools/add_spdx_headers.py` to apply uniformly; the script is
  idempotent.

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the practical onboarding flow.

---

## Escalation path

For disputes, code-of-conduct violations, or governance concerns:

1. **Open an issue tagged `governance`** describing the concern.
2. **Direct contact** as a last resort:
   [jagannivas.001@gmail.com](mailto:jagannivas.001@gmail.com). Code-of-conduct
   reports go directly to this address per [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).

The BDFL adjudicates. Future Phase 2/3 evolution will distribute this
authority across Maintainers / Steering Committee respectively (see below).

---

## Future evolution

KaraOS commits to a 3-phase governance evolution path. Phase transitions are
triggered by contributor-base growth, not calendar dates.

### Phase 1 — BDFL (current)

Single adjudicator: Jagannivas. Active until Phase 2 trigger fires.

### Phase 2 — BDFL + Maintainers + Committers

**Trigger:** 3 or more regular external contributors (defined as contributors
who land 5+ non-trivial PRs over a 6-month window).

**Structure:**

- BDFL retains final authority on project direction and tie-breaks.
- 2-3 Maintainers (appointed by BDFL from the regular-contributor pool) own
  code-review authority on their respective subsystems.
- Committers (3+ regular contributors) have direct merge rights on PRs they
  did not author, contingent on Maintainer approval.

**Maintainer responsibilities:** code review, test gate enforcement, release
sign-off, strict-mode discipline reference for spec-track work.

### Phase 3 — Steering Committee (PEP-8016-style)

**Trigger:** 10 or more active Committers.

**Structure:** Steering Committee elected from the Committer pool annually,
governance modeled on Python's PEP-8016 (5-member committee, term limits,
public election process, conflict-of-interest disclosures).

BDFL transitions to an honorific role (project founder + advisor) at this
phase. Day-to-day adjudication moves to the Steering Committee.

---

## Trademark and branding

The KaraOS name is owned by the project. Downstream forks that diverge in
direction from the upstream BDFL/Steering decisions should rename to avoid
trademark confusion. Apache 2.0 (the project's license) permits forking; the
name is the only branding asset reserved for the upstream project.

---

## Governance change process

Changes to this document follow the same RFC process as architectural
proposals: issue first, public discussion, BDFL adjudication. Significant
governance shifts (e.g., Phase 1 → Phase 2 trigger criteria) require a
2-week public-comment window before adjudication.

---

**Last updated:** 2026-05-28 (Pre-P1 Bundle 2 — Governance landed; Phase 1
BDFL documented; Phase 2/3 evolution criteria locked).
