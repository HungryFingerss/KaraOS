# Pre-P1 Bundle 1 — Docs + CI Phase 0 Audit (2026-05-27)

**Cycle**: Pre-P1 must-fix Bundle 1 (Docs+CI)
**Items**: MF1 (CI scaffold verify + remediate) + MF3 (CLAUDE.md Layer D rewrite) + MF10 (everything_about_system.md split)
**Discipline**: Strict-mode, OPTIONAL-Plan-v2 path candidate (clean cycle)
**Architect**: Claude
**Auditor**: External
**Predecessor**: P0.S10/S11/S12 closure 2026-05-27

---

## §0 Procedural commitments

Per `### Architect-reads-production-code-before-sign-off` + sub-rule 1+3 locked at P0.R10-R15:

1. **Path C grep-verify discipline applied at closure-narrative drafting time** (production code + memory file paths + MEMORY.md index entries + `to_be_checked.md` via PowerShell fresh-disk read).
2. **Cross-path memory-file discipline** applied to any new memory file landing this cycle (BOTH `C:\Users\jagan\.claude\projects\C--Users-jagan-dog-ai\memory\` + `C:\Users\jagan\.claude\projects\C--Users-jagan-dog-ai-dog-ai\memory\`).
3. **Closure-audit verdict forwarding** to auditor for explicit ratification BEFORE declaring CLOSED.
4. **Multi-discipline preventive convergence sub-rule elevation candidacy** — 6 instances banked at P0.S10 closure; STRONGLY WARRANTED at next major architect-side narrative work. Bundle 1 closure-audit is a candidate elevation event if 5+ disciplines apply preventively this cycle.

---

## §1 Pass-1 grep-verified findings

### §1.1 MF1 — CI scaffold current state

**Grep evidence** (verified `.github/workflows/*.yml` + `pytest.ini` 2026-05-27):

| File | Status | Trigger | Pytest scope |
|---|---|---|---|
| `.github/workflows/fast.yml` | ✅ EXISTS | every push + PR | `not slow and not network and not models and not privacy_critical` + dedicated privacy_critical step with fail-on-skip |
| `.github/workflows/slow.yml` | ✅ EXISTS | nightly 03:30 UTC + manual | full suite incl. slow + models + network (TOGETHER_API_KEY-gated) |
| `.github/workflows/security.yml` | ✅ EXISTS | weekly Sunday 04:00 UTC + push to main on requirements changes | pip-audit + Trivy SARIF |
| `.github/workflows/trufflehog.yml` | ✅ EXISTS | PR diff + Sunday full-history | TruffleHog `--results=verified` |
| `pytest.ini` | ✅ EXISTS | — | 4 markers registered: `network`, `slow`, `models`, `privacy_critical` |

**Informational-mode gates** (currently non-blocking; `|| true` or `continue-on-error: true`):
- `mypy` — permissive mode, allow-list mode
- `ruff format --check` — first-rollout, will block after repo-wide format pass
- `pip-audit` — first-pass baseline, will tighten to `--strict` after CVE backlog triage
- Trivy `exit-code: 0` — reports findings to Security tab, does not fail build

**Currently BLOCKING gates**:
- `ruff check` (lint) — fails CI on rule violations
- Fast pytest subset — fails on any test failure (`--maxfail=5`)
- Privacy-critical pytest — fails on any failure AND on any skip
- TruffleHog — fails on any verified credential finding

**Pass-1 audit conclusion**: CI scaffold landed at P0.0 (2026-05-08) is **structurally complete**. The audit's "CRITICAL" framing under MF1 reflects that **architect verification has not happened since P0.0** — workflows exist but no documented evidence of recent green runs. Stale entry in `CLAUDE.md` Pending Work line 113:

> **P1.P1 — No CI config**: no `.github/workflows/` directory exists.

This is **factually wrong** as of 2026-05-27. CLAUDE.md doc-currency drift.

### §1.2 MF3 — CLAUDE.md Project Overview current state

**Grep evidence** (CLAUDE.md:977-986):

```
## Project Overview

AI robot dog. Sees faces → identifies people → greets by name → holds voice conversations → remembers people across sessions.

**Dev machine:** Windows 11 laptop (DirectShow camera)
**Production target:** Jetson AGX Orin 32GB (V4L2, faiss-gpu, TensorRT)
**Project root:** `C:\Users\jagan\dog-ai\dog-ai\`
**Run:** `python pipeline.py`
**Venv:** `venv\Scripts\activate` (Windows) / `source venv/bin/activate` (Linux)
**Tests:** `pytest` (1273 passing, asyncio_mode=auto)
```

**Audit framing**: "AI robot dog" is a COMPANION framing. Audit's strategic reframe positions KaraOS as Layer D cognitive middleware (above motor control, below natural language) — a robot-agnostic runtime, not a single dog product.

**Required rewrite shape** (per CEO decisions doc §1):
- Lead with "Layer D cognitive runtime middleware" framing
- Two-stack architecture explicit (companion + robotics)
- Companion stack = today's behavior (AI robot dog example)
- Robotics stack = embodied runtime landing in P1 (TurtleBot4 reference)
- Reference 3-5 year horizon claim
- Preserve dev/production/run/venv/tests practical references (no churn there)

### §1.3 MF10 — everything_about_system.md current state

**Grep evidence**:
- File size: **6487 lines / 608 KB**
- H2 section count: **178 sections**
- Table of Contents at line 44
- Content sections start at line 493 (§1 What Kara-OS Is)
- Final section: §176 `addressed_to` Column on `conversation_log` at line 6517

**Natural section clusters** (identified from section listing):

| Cluster | Sections | Line range | Approx size | Domain |
|---|---|---|---|---|
| C1 — Introduction + Tech Stack | §1-§9 | 493-1115 | ~620 lines | What it is, philosophy, tech stack, install, startup |
| C2 — Lifecycle + Pipeline States | §10-§15 | 1116-1393 | ~280 lines | First boot, daily flow, shutdown, factory reset, states |
| C3 — Async + Vision Basics | §16-§29 | 1394-1935 | ~540 lines | Event loop, scene heartbeat, RetinaFace, SORT, AdaFace, lip tracking, mic, VAD |
| C4 — Audio + STT/TTS | §30-§35 | 1936-2102 | ~170 lines | Smart-Turn, echo skip, Whisper, diarization, Kokoro/Piper, sentence streaming |
| C5 — Face/Voice Galleries | §36-§46 | 2103-2422 | ~320 lines | FaceDB, FAISS, recognition, ECAPA, voice gallery, self-update, pruning |
| C6 — Sessions + Evidence | §47-§58 | 2423-2924 | ~500 lines | SessionStore, person_type, open/close, expiry, primary selection, evidence dataclass |
| C7 — Reconciler + Conversation Turn | §59-§71 | 2925-3437 | ~510 lines | Reconciler cascade, routing thresholds, scene block, stranger workflow, conversation_turn anatomy, prompt composition |
| C8 — Prompt Blocks + Brain Agents | §72-§99 | 3438-4359 | ~920 lines | Full prompt catalog, brain.db schema, 14 agents, dream loop |
| C9 — Dispute + Tool Privileges + Logging | §100-§118 | 4360-4633 | ~270 lines | Uncle incident, disputed state, tool privileges, log_utils, anti-spoof summary |
| C10 — Schemas + Tests + Dashboard | §119-§140b | 4635-5161 | ~530 lines | faces.db, brain.db, FAISS, Kuzu, state.json, tests, dashboard architecture |
| C11 — Future Work + Reference Tables | §141-§149 | 5164-5704 | ~540 lines | ReSpeaker, Jetson, wake word, robot.py, glossary, config table, tool schemas, session history |
| C12 — Privacy + Rooms + Recent Work | §150-§176 | 5705-6517 | ~810 lines | 4-tier privacy model, visibility clause, owner access, room block, turn arbitration, session-end synthesis |

**Pass-1 audit conclusion**: ~12 natural clusters. Audit recommends splitting to `docs/architecture/CHAPTER_NN_*.md` files with a parent index. Whether to split into 6 (coarse) or 12 (fine) is a Plan v1 question.

### §1.4 Stale CLAUDE.md references requiring update

Grep-verified entries that become STALE post-Bundle-1:
- Line 113 (Pending Work): "P1.P1 — No CI config" — factually false; CI exists
- Line 977 (Project Overview): companion-only framing — Layer D rewrite
- Any reference to `everything_about_system.md` as a single file (multiple sites) — must update to chapter pointer

---

## §2 D-decisions surfaced

### D1 — MF1 — CI scaffold verification + CLAUDE.md remediation

**Sub-decisions**:
- **D1.a**: Architect (Claude) declares MF1 verification COMPLETE per the §1.1 grep evidence above (4 workflows + 4 markers + structural-invariant test runs in fast.yml). No code change required.
- **D1.b**: Remove stale `P1.P1 — No CI config` entry from CLAUDE.md Pending Work section.
- **D1.c**: Add NEW CLAUDE.md narrative entry confirming P0.0 CI scaffold is live + identifying the 4 informational-mode gates as deferred-tightening candidates (NOT P1 scope; flagged for post-P1 follow-up).

**Open question to auditor** (Q1): should D1.a require a fresh CI run as evidence (user-triggered manual workflow_dispatch on slow.yml) before declaring MF1 complete? Architect lean: YES — request user to trigger `workflow_dispatch` on slow.yml + report green/red status. Path-of-least-evidence to confirm the scaffold actually works end-to-end, not just exists on disk.

### D2 — MF3 — CLAUDE.md Project Overview Layer D rewrite

**Scope**: Replace lines 977-986 with new framing.

**Required content** (per CEO decisions doc):
- **Lead sentence**: KaraOS as Layer D cognitive runtime middleware for embodied AI
- **Two-stack explicit**: companion stack (current) + robotics stack (P1)
- **Companion description**: "AI robot dog" framing demoted to ONE EXAMPLE of the companion stack — Kara is the reference application, not the project
- **Robotics description**: embodied runtime + TurtleBot4 reference (per CEO decisions)
- **Strategic positioning**: 3-5 year market-defining horizon (verbatim from CEO decisions)
- **Practical references PRESERVED**: dev machine + production target + project root + run + venv + tests (no churn here)

**Open question to auditor** (Q2): should the rewrite ALSO update the "Architecture" section (lines 990+) to show the embodied runtime components as future (commented "P1 LANDING" placeholder rows)? Architect lean: NO — that's P1 scope, not pre-P1. Pre-P1 only rewrites the framing paragraph. Architecture-diagram changes land WITH the P1 specs that build those components.

### D3 — MF10 — everything_about_system.md split

**Scope**: Split into `docs/architecture/` chapter files per §1.3 cluster table.

**Open question to auditor** (Q3): coarse-split (6 files) or fine-split (12 files)?

**Architect lean**: **fine-split (12 files)**, one per natural cluster. Rationale:
- Each cluster averages ~400-900 lines = comfortable file size
- Each chapter's domain is single-axis (sessions OR vision OR brain agents) — preserves reader's mental model
- Coarse-split risks recreating the original problem (one or two files balloon back to 1000+ lines)
- 12 files maps clean to 12 natural sub-domains the architect/auditor already reason about

**Companion deliverables under D3**:
- `docs/architecture/README.md` — parent index linking to all chapters with one-line summary per chapter
- Original `everything_about_system.md` REPLACED with a thin redirect: brief "this file split to `docs/architecture/`" + chapter links
- CLAUDE.md references to `everything_about_system.md §NNN` updated to `docs/architecture/CHAPTER_NN_*.md §NNN` (line-shift discipline)

**Open question to auditor** (Q4): should the thin redirect in `everything_about_system.md` stay long-term, OR should the file be deleted entirely with all in-tree references updated?

**Architect lean**: **thin redirect stays**. Rationale:
- Preserves any external bookmark/reference that points to the old path
- Stops accidental future writes from re-growing it (the redirect contains a clear "DO NOT WRITE HERE — see chapters" notice)
- Costs ~20 lines of stub vs deletion

### Cross-D shipping order

**Architect lean**: **D3 → D2 → D1**. Rationale:
- D3 (split) is the biggest mechanical surface (12 file creations + 178 H2 sections to relocate). Land FIRST while CLAUDE.md still references the old path — fewer ripple updates.
- D2 (CLAUDE.md rewrite) follows because its Architecture section may reference `docs/architecture/`
- D1 (CLAUDE.md Pending Work cleanup) is last — small, one-line removal + one-line addition

---

## §3 Anchor count estimate (Q5 MID-RANGE methodology)

**Per-D estimate**:

| D-decision | Anchor type | Mid count | NARROW band [±15%] |
|---|---|---|---|
| D1.a — CI verification declaration | architect-narrative (no test) | 0 (doc-only) | — |
| D1.b — Pending Work stale-entry removal | source-inspection: stale line ABSENT | 1 | [0.85, 1.15] |
| D1.c — NEW narrative confirming CI live | source-inspection: confirmation present | 1 | [0.85, 1.15] |
| D2 — CLAUDE.md Layer D rewrite | source-inspection: key phrases present (5 phrases × verbatim substrings) | 3 | [2.55, 3.45] |
| D3 — everything_about_system split | source-inspection (3) + structural (2) | 5 | [4.25, 5.75] |
| Cross-cutting — CLAUDE.md ref updates | source-inspection: zero stale `everything_about_system.md` refs in CLAUDE.md outside the redirect | 1 | [0.85, 1.15] |

**Total Q5 mid**: 11 logical anchors.
**NARROW band [±15%]**: [9.35, 12.65].
**Q5 LOCK at mid 11 with ±15% tolerance**.

D3 anchor breakdown (the largest):
- A1 (source-inspection): `docs/architecture/` directory exists with 12 chapter files
- A2 (source-inspection): parent index `docs/architecture/README.md` lists all 12 chapters with one-line summaries
- A3 (source-inspection): `everything_about_system.md` is now a thin redirect (< 50 lines) with explicit "see chapters" notice
- A4 (structural): each chapter file is self-contained — H2 sections from §1.3 cluster table land in the correct chapter (parametrize fan-out across 12 chapters = ~12-15 collections)
- A5 (structural): zero broken cross-references — every `§NNN` reference in CLAUDE.md and other docs resolves to a valid chapter+section pair

**Closure-projection band table** (per `Explicit-closure-honest-count-commitment` discipline):

| Closure-actual | % vs mid | Reading | Doctrine consequence |
|---|---|---|---|
| 9 anchors | -18.2% | SLIGHT-DRIFT-DOWN | Within ±30% falsification tolerance; doctrine holds |
| **11 anchors (Q5 LOCK)** | **0% — ON-TARGET** | exact mid | `### Phase-0-granular-decomposition-enables-accurate-estimates` bumps; **10th consecutive 0%-streak rebuild** under `Doctrine-prediction-precision-improving-over-arc` sub-observation |
| 12 anchors | +9.1% | ON-TARGET (within NARROW band) | doctrine bumps |
| 13 anchors | +18.2% | SLIGHT-DRIFT-UP | Within ±30% falsification tolerance; doctrine holds |
| ≥15 anchors | +36.4% | FALSIFICATION TRIGGER | `### Phase-0-granular-decomposition` falsification clause activates IF root cause is wrong-premise; if scope-expansion via auditor refinement, sub-observation reset only |

**Plan v1 §6 honest-count commitment**: closure narrative MUST report closure-actual against mid 11 explicitly with %-delta + doctrine consequence per the band table.

---

## §4 Cross-spec impact

### §4.1 Specs affected by D3 (file-relocation surface)

Grep-search target list for Plan v1 §1 Pass-2 (to enumerate ALL references that will need update):
- CLAUDE.md (already known)
- `tests/p0_*_audit.md` + `tests/p0_*_plan_v*.md` — many spec files reference `everything_about_system.md §NNN` for context
- `to_be_checked.md` — may reference
- `complete-plan.md` (parent) — may reference
- `karaos-org-discussions/*.md` — external audit may reference
- `core/` source code docstrings — probably zero references but worth grep
- `tests/` test docstrings — same

**Architect projection**: ~10-30 references across spec + plan files. Plan v1 enumerates exhaustively at §1.2.

### §4.2 Specs NOT affected

- Production code (`core/`, `pipeline.py`) — zero references to `everything_about_system.md` expected
- `requirements.txt`, `pytest.ini`, `setup.py` — no doc references
- Tests under `tests/test_*.py` — typically reference spec files, not the architecture doc

### §4.3 Bundle 2-5 dependencies

- **Bundle 2 (Governance — MF2)**: depends on D3 split (so SPDX headers reference per-chapter ownership) — but actually NO, SPDX headers go on source files, not docs. **Independent.**
- **Bundle 3-5**: code-only work. No dependency on Bundle 1 docs.

Bundle 1 → Bundle 2 → 3 → 4 → 5 can run sequentially OR Bundle 1 + Bundle 2 in parallel (both docs-side).

---

## §5 Discipline counts to bump (per locked +1-per-artifact convention)

**Pre-Bundle-1 baselines** (verified at P0.S10 closure 2026-05-27):

| Discipline | Pre-Bundle-1 | After Phase 0 | After Plan v1 | After closure |
|---|---|---|---|---|
| Strict-industry-standard mode applications | 110 | 111 | 112 | 113 |
| Strict-industry-standard mode closures | 32 | 32 | 32 | 33 |
| Spec-first review cycle | 119 | 120 | 121 | 122 (3-artifact OPTIONAL-Plan-v2 cycle) |
| `### Grep-baseline-before-drafting` | 77 | 78 | 79 | 80 |
| Cross-cycle-handoff transparency | 80 | 81 | 82 | 83 |
| Spec-time grep-verification | 87 | 88 | 89 | 90 |
| `### Twin-filename-pitfall-prevention` | 31 | — | — | 32 (preventive — Bundle 1 artifacts at `tests/pre_p1_bundle1_*.md` cleanly disambiguated against zero pre-existing pre_p1 artifacts) |
| `### Architect-reads-production-code-before-sign-off` | 30 | — | — | 31 (closure-audit event; explicit X → Y line per `Implicit-doctrine-firings-not-narrative-tracked` sub-rule) |
| Auditor-Q5-estimates-trail-grep | 36 | — | — | 37 banked closures (at projected 0% ON-TARGET — 10th consecutive 0%-streak) |
| Deferred-canary strategy | 34 | — | — | 35 applications (Bundle 1 entry pasted into `to_be_checked.md`) |

**Discipline candidate firings this cycle**:
- `### Phase-0-granular-decomposition-enables-accurate-estimates`: BUMP 38 → 39 supporting at closure IF Q5 lands ON-TARGET
- `Doctrine-prediction-precision-improving-over-arc` sub-rule: 9 → 10 consecutive 0%-streak instance IF Q5 closure-actual = 11 exact
- `Multi-discipline preventive convergence` sub-rule (CANDIDATE ELEVATION at this closure-audit): 6 → 7 instances WARRANTED at Bundle 1 closure if 5+ disciplines apply preventively. **STRONGLY WARRANTED if 7th instance lands**.

---

## §6 Open questions for auditor

Same enumeration as inline above for clarity:

**Q1** (D1.a evidence bar): require user-triggered `workflow_dispatch` on slow.yml + green/red report before declaring MF1 complete? Architect lean: YES.

**Q2** (D2 scope): rewrite Architecture section too, or only the Project Overview paragraph? Architect lean: ONLY Project Overview paragraph. Architecture section changes land WITH P1 specs.

**Q3** (D3 granularity): coarse-split (6 files) or fine-split (12 files)? Architect lean: FINE-SPLIT (12).

**Q4** (D3 deletion vs redirect): delete `everything_about_system.md` entirely, or keep as thin redirect? Architect lean: THIN REDIRECT.

**Q5** (cross-D order): D3 → D2 → D1 shipping order, or different? Architect lean: D3 → D2 → D1.

**Q6** (Q5 LOCK): mid 11 with ±15% NARROW band, OR auditor's preferred reading? Architect lean: mid 11 LOCK.

**Q7** (Plan v2 path): if auditor returns 0 precision items, take OPTIONAL-Plan-v2 path (skip Plan v2, ship Plan v1 to developer)? Architect lean: YES — Bundle 1 is doc work with no behavioral surface; clean cycle structurally expected.

---

## §7 Architect closure-projection commitment

Per `Explicit-closure-honest-count-commitment` discipline (LOCKED at P0.B3 closure 2026-05-21; 31 instances at P0.S10 closure):

- IF closure-actual = 11 exact: doctrine `### Phase-0-granular-decomposition` BUMPS 38 → 39 supporting + sub-observation `Doctrine-prediction-precision-improving-over-arc` extends 10th consecutive 0%-streak.
- IF closure-actual ∈ {9, 10, 12, 13}: doctrine HOLDS at 38 supporting; sub-observation streak interrupted; honest closure-actual reading reported.
- IF closure-actual ≥ 15 OR ≤ 7: FALSIFICATION-WATCH activates; closure-audit must surface root cause (scope-expansion vs wrong-premise) before doctrine consequence is locked.

Architect publicly commits to honest closure-actual reporting at Phase 7 closure-narrative drafting regardless of which band falls.

---

## §8 Plan v1 §1 Pass-2 grep refresh commitment

Per `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` doctrine (elevated at P0.R4 closure 2026-05-23; 14 applications at P0.S10 closure):

Plan v1 §1 will re-grep:
- `.github/workflows/*.yml` for fresh state confirmation
- CLAUDE.md `everything_about_system.md` reference enumeration (for D3 ripple table)
- All spec/plan files under `tests/` for `everything_about_system.md` references
- `karaos-org-discussions/*.md` for any audit references to the file
- `complete-plan.md` (parent) for references

3-part Pass-2 grep operational rule (locked at P0.S10 Plan v4):
1. Symbol-name-uniqueness grep (D2 phrase verbatim substrings — no collision with surrounding text)
2. Behavioral semantic verification under call-site context (D3 chapter-section mapping verified empirically by reading each cluster's content + confirming H2 sections land in the right chapter)
3. Symmetric verification of reject + preserve classes (D3 cross-reference test: every `§NNN` ref resolves to a valid chapter+section AND no spurious chapter file mentions sections not in its assigned cluster)

---

## §9 Closure-audit forwarding commitment

Per `### Architect-reads-production-code-before-sign-off` sub-rule 3 (closure-audit verdict cycle elision resolution, 5-cycle routinization at P0.S10 closure):

Bundle 1 closure-audit findings will be forwarded to auditor for EXPLICIT RATIFICATION verdict BEFORE declaring CLOSED. 6th cycle of consecutive routinization. Sub-rule elevation candidacy strengthens.

---

## §10 Recommended auditor verdict shape

```
VERDICT: ACCEPT / ACCEPT WITH PI / BLOCKED

For ACCEPT or ACCEPT WITH PI:
  - Approve Q5 LOCK at mid 11 ± 15% NARROW band
  - Approve cross-D shipping order (D3 → D2 → D1) or override
  - Adjudicate Q1-Q7 with explicit lean per question
  - Identify any §1 grep-verified findings architect missed
  - Decide OPTIONAL-Plan-v2 eligibility

For BLOCKED:
  - List Precision Items (PIs) with exact §reference
  - Specify which D-decision needs absorption at Plan v1
```

---

Standing by for auditor verdict on Phase 0.

**Architect closure-audit commitment**: Plan v1 will absorb auditor PIs at §1.4 (revised cluster table if granularity changes) + §2 (revised D-decisions) + §3 (Q5 re-lock with auditor-final mid value). Closure-narrative honest-count commitment honored regardless of which band Q5 lands in.

---

**Filed**: 2026-05-27
**Architect**: Claude
**Forwarded to**: Auditor (external)
