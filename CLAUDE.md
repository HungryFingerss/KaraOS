# DOG-AI — Claude Working Memory

> ## ⚠ READ THIS BLOCK FIRST — it is the current state. Everything below it is historical archive.
>
> **Last updated: 2026-07-30.**
>
> **FILE-SIZE DEFECT (recorded 2026-07-30, needs a decision):** this file is
> **1,034 KB**, and the single historical-narrative line below is **522 KB**.
> Claude Code truncates on load, so **most of this file is invisible in any
> session** — the same silent-truncation failure the memory index hit at 24 KB,
> 40× larger. That is why the current-state block lives HERE, above the giant
> line. Proposed remedy (awaiting Jagan's go-ahead): split the per-session
> narrative into `docs/history/` and keep this file to current state + rules +
> disciplines + pending work (~40 KB, loads whole). Until then: anything that
> must be read every session goes in THIS block.
>
> ### ACTIVE CYCLE — SB.2-LLM: local-primary brain (Ollama gpt-oss:20b), Together.ai secondary
>
> Goal: invert the stack so the LOCAL model is the primary brain with every
> feature Together.ai has today, cloud fires only on genuine local failure.
> One switch (`profiles/companion.yaml` → `llm: {provider: local, fallback:
> cloud}`). Locked principles: quality over speed; the 24 GB-VRAM user is the
> primary persona; **zero cloud calls while local is healthy**; model name is
> pure config.
>
> **Full spec + all 17 rulings addenda:** `rule book/cycle-specs/sb2_llm_phase2_corpus_spec.md`
> (plus `..._phase0_probe_spec.md`, `..._phase0_1_reprobe_spec.md`,
> `..._phase1_mechanism_spec.md`). Hardware/validation strategy:
> `rule book/RENTED-GPU-VALIDATION.md`.
>
> **Branch + push state:** all work on `sb2-llm-local-flip`, **45+ commits,
> UNPUSHED on both remotes** (verified 2026-07-29), no tracking branch, held at
> Jagan's instruction. `main` is byte-identical to `origin/main` and still
> `provider: cloud` — a fresh clone + `TOGETHER_API_KEY` behaves exactly as
> before the cycle.
>
> **Test state (honest):** last VERIFIED green full suite **5187 passed / 0
> failed**. A later `core/brain.py` edit produced 2 failures (the P0.S5
> `_INDIRECT_BOUNDARIES_ALLOWLIST` LINE-REF-DRIFT ripple), fixed in isolation,
> **full suite not yet re-run**. Per `Full-suite-run-is-the-universal-
> completeness-proof`: no sweep until an actual green run.
>
> **LANDED:** provider/fallback bundles + `FALLBACK_*` leaves + keyless-boot
> validation · `_LLMTarget` + single `_fallback_target()` purity chokepoint ·
> `karaos-gptoss` derived tag (num_ctx 8192) · request shaping
> (`LOCAL_MAX_TOKENS`, `reasoning_effort: low`) · null-response detector ·
> agent-layer shaping + `LOCAL_AGENT_TIMEOUT_SECS` · `LOCAL_CHAT_TIMEOUT_SECS
> =120` (7 sites, target-aware) · `LOCAL_CLASSIFIER_TIMEOUT_SECS=30` ·
> `config.auth_headers` (11 sites — keyless `Authorization: Bearer ` was FATAL)
> · D2 shutdown structural gate (shared predicate, both paths) · D3 arg-key +
> blank-args gates · `GRAPH_LOCAL_EMBEDDING_DEVICE="cpu"` · real drain barrier
> · OOM-aware status · boot VRAM check · fingerprint hardening (config keys +
> runner SHA) · sim async migration + vacuous-test rebuild.
>
> **MEASURED:** B.2 intent 76% hybrid, all 4 gating intents green · B.4 sim A/B
> **ASSERT parity 100% (11/11 assert-bearing), exit-code 100% (18/18), zero
> divergent labels** · B.5 extraction 66.7% structured — FAIL-accepted, named
> limitation · probes 30/30 exact tool args, 35/35 JSON, warm TTFT 2-5 s.
> Quality figures are valid; **every LATENCY figure from this box is a hardware
> artifact** (14 GB model on 8 GB VRAM → 58% CPU offload, permanent).
>
> **FOUND (the cycle earning its keep):** the Friends benchmark metric rewards
> never-answering — corrected ranking INVERTS the published claim (70B 57.89 >
> graph 44.82 > local 36.90); a public honesty annotation is MANDATORY before
> those numbers are quoted again · `GRAPH_CLASSIFIER_MODE` stays `"shadow"`
> (**commit B SHADOW-HOLD**) because the graph has no injection defense and
> promoting it opened an injection→shutdown path · **D3(a) was unreachable in
> production** (guarded by a condition its own target defect makes false) ·
> **5 vacuity instances** · 4 would-have-shipped defects.
>
> **PENDING:** D3(a) reachability fix + AST invariant + caller-path test ·
> classifier-degradation contract (P0, own spec) · full 18-script sweep
> (assert-bearing first) · blind judge (instrument control first) · Auditor
> Review 2 · **Phase 3 = ONE commit** (`companion.yaml` → local) · Phase 4 live
> canary. Filed post-cycle: teardown race · harness-resilience audit (5
> species) · briefing fabrication fix · published-claims annotation.
>
> ### Cadence rule (added 2026-07-30 at Jagan's instruction)
>
> **Update this block at every PHASE closure, not just at cycle end.** The
> earlier policy ("SB detail lives in the tracker, this banner is intentionally
> stale") is SUPERSEDED — the tracker it names is gitignored and 4 weeks stale,
> so that policy left the truth nowhere. `everything_about_system.md` stays on
> its own end-of-cycle cadence.

---

## Historical record — moved to `docs/history/` (2026-07-30)

The per-session closure narratives, the completed-sessions table, the
2026-04-10 bug audit, and the closed board-bug track were moved out of this
file on 2026-07-30. CLAUDE.md had reached **1,029 KB with a single 522 KB
line**, so Claude Code truncated it on load and most of it was never read in
any session — the same silent-truncation failure the memory index hit at
24 KB. **Nothing was deleted.** Index: `docs/history/README.md`.

| what | where |
|---|---|
| Per-cycle closure narratives (SB.1, Pre-P1 bundles, P0.R/P0.S/P0.B arcs, canaries) | `docs/history/CLOSURE-NARRATIVES.md` |
| Session-by-session table (Sessions 1-122) | `docs/history/COMPLETED-SESSIONS.md` |
| 2026-04-10 full bug audit (all resolved) | `docs/history/BUG-AUDIT-2026-04-10.md` |
| Board-bug remediation track (CLOSED 2026-05-21) | `docs/history/BOARD-BUG-TRACK.md` |

## Rules for Claude

- **Never start development until Jagan explicitly says to.** Always discuss and align first.
- **WRITE EVERY IMPLEMENTATION INTO `docs/history/` — always, at the time it lands (Jagan, 2026-07-30).** Whatever we implement, whenever we implement it: a phase closes, a fix lands, a defect is found, a ruling is made → it goes into the active cycle file under `docs/history/` in the same session. Not at cycle end. Not "later". Each entry carries what changed (files/functions, not just prose), the commit hash, WHY (the defect or requirement that forced it), the evidence that it works — or the honest state if unproven, what was decided against and why, and any known limitation. Never rewrite history to look cleaner: corrections are appended with the correction visible, because a wrong diagnosis that got caught is itself part of the record. Conventions + layout: `docs/history/README.md`.
- **Update the current-state block at the TOP of this file at every PHASE closure** — not just at session end. It sits above the bulk specifically so it survives load truncation.
- **SUPERSEDED 2026-07-30 (kept for the record):** the old rule said the SB live status lives in `karaos-org-discussions/solidify-base/00-SEQUENCE-STATUS.md` and that this banner is "intentionally NOT updated per-SB-cycle (stale at SB.1 by design)." That tracker is **gitignored and stale since 2026-07-02**, so the policy left the truth recorded nowhere and an entire cycle (SB.2-LLM, 45+ commits) went unlogged. The current-state block above plus `docs/history/` replace it. The board spec at `karaos-org-discussions/solidify-base/00-BOARD-MEETING-SOLIDIFY-FINAL-2026-06-03.md` remains valid as a reference.
- Never leave stale values in this file. Verify against source code before writing.
- **Keep this file loadable.** It hit 1,029 KB on 2026-07-30 and was being silently truncated on load — most of it unread in every session. Historical narrative belongs in `docs/history/`, architecture reference in `docs/architecture/`. If this file grows past ~200 KB, split again rather than letting it become unreadable.
- always use the skills, hooks, plugins, tools, etc. provided to you. and if needed any more, always ask jagan to provide them.
- never implement hardcodings, predefined rules. in this project, all the decisions should be decided by brain, always plan and implement in that way. NO HARDCODINGS.

---

## Architectural Disciplines

Named patterns elevated from recurring practice into explicit doctrine. Each name maps to a multi-cycle empirical track record; future sub-PRs must apply the named discipline when its trigger conditions match.

### Induction-surfaces-invariant-gaps

Every structural invariant ships with an induction protocol that deliberately exercises the failure mode it is meant to prevent. The induction is the test of the invariant, not the test of the production code. When induction surfaces a gap (either in the invariant's coverage or in production code), the gap is closed in the same cycle, not deferred.

**Track record (batting 7-for-7):**
- **P0.6.7v2** — 8 deliberate-regression checks induced field-drift / unenumerated-writer / paired-write-atomicity / producer-copy / peek-not-mutate / ratchet / M2-coverage / prior-state-guard violations; all 8 fired correctly.
- **P0.8.2** — F1 + F2 deliberate-regression: injected sync `.execute()` loop without checkpoint + flipped `include_tools=False` → `True`; both invariants fired correctly.
- **P0.11** — 3 deliberate-regression checks (subscript-revert / global-decl drop / external-module attribute-form injection); the third surfaced a detector gap (attribute-form access not caught) → detector strengthened in same cycle.
- **P0.12** — Hypothesis property tests (1000 examples/test) induced two real production bugs: `_parse_json` returned non-dict types (contract violation); `_parse_intent_sidecar` didn't catch Python 3.11+ `ValueError` on oversized int strings. Both fixed in same sub-PR with regression tests pinned to falsifying inputs.
- **P0.12.1** — caller-audit surfaced one real downstream regression (`SocialGraphAgent` list-shape branch became unreachable after P0.12); fix landed in same cycle via sibling `_parse_json_array`.
- **P0.0.1** — known-gap review surfaced false-premise tripwire (S2 dashboard `--hostname` absence allowed LAN binding because Next.js defaults to `0.0.0.0`); fix tightened tripwire to require explicit-localhost-bind, same cycle.
- **P0.0.2** — alignment test confirmed via 3 induced regressions (forced xfail to pass / removed decorator / restored); all three fired correctly with full S2-style remediation messages.

**Auditor adjudication 2026-05-18 — HOLD at 7-for-7, do not bump on P0.S1.** The architect's P0.S1 closure flagged a borderline 8th instance candidate citing (a) 3/3 deliberate-regression confirmations at Phase 4 closure, (b) the Plan v2 §11 5-vs-18 test-fan-out calibration miss, and (c) the VisionFramePayload widening surfacing via the existing P0.0.7 invariant. The auditor took the stricter read: induction-surfaces-invariant-gaps counts instances where the protocol catches something *previously unknown* — a coverage gap, an unsuspected production bug, an edge case the developer hadn't pre-flagged. (a) is the protocol firing on KNOWN invariants (routine, not a count event); (b) is an estimation calibration miss, not an invariant gap; (c) is a known-intentional schema change where the invariant correctly refused silent drift (the invariant doing its design job, not surfacing a gap). Conflating any of these with the count erodes its signal value. The VisionFramePayload widening is fully counted under developer-improves-on-spec (no double-count across disciplines). P0.S1 contribution to this track record: zero. Stays 7-for-7.

**Operational rules:**
1. Every new structural invariant gets a deliberate-regression check before sign-off — induce the violation, confirm the test fires, revert, document the outcome in the closure report.
2. Mid-flight production fixes from induction findings are NOT scope creep — they are the protocol working. Document them in the same sub-PR.
3. When induction surfaces a detector gap (the invariant didn't catch a real violation), strengthen the detector in the same cycle. Do not defer.
4. Property-based testing (Hypothesis) is a first-class induction tool, not a quality nice-to-have. Use `max_examples=1000` for contract surfaces.

### Architect-reads-production-code-before-sign-off

Reviewer / auditor sign-off requires reading the actual implementation against the closure summary. Summaries describe intent; code reveals what shipped. Closure narratives can drift from grep-verifiable reality at multiple surfaces (production code, memory files, deferred-canary tracking artifacts). The discipline is bidirectional: architect catches developer's claim-vs-reality drift; auditor catches architect's claim-vs-reality drift.

**Track record (34 instances at Pre-P1 Bundle 4 closure-audit 2026-05-28):**

Original track record (3 instances pre-P0.S2): P0.6.7 v1→v2 (three real gaps surfaced by post-closure audit including vision-globals migration miss, CacheStore touch-on-read LRU violating the locked spec, and 4th-shim miscounted disclosure); P0.7 closeout caller audit (187 legacy patterns in test_pipeline.py surfaced after 1717-passing milestone); P0.12.1 (Site B dead branch surfaced from post-closure caller audit).

Subsequent banking 2026-05-20 → 2026-05-28: 31 additional instances across P0.S2/S3/S4/S5/S6/S7/S8/S9/B-arc/R-arc closure-audits + Pre-P1 Bundle 1 + Bundle 2 + Bundle 3 + Bundle 4 closure-audits. Each instance applied Path C grep-verify discipline against production code + memory files + deferred-canary tracking artifacts at closure surface. **Bundle 2 closure-audit 2026-05-28 added 1 instance (32nd)** with simultaneous Sub-rule 4 BIDIRECTIONAL-VALIDATION elevation event lock per 3-instance threshold reached. **Bundle 3 closure-audit 2026-05-28 added 1 instance (33rd)** (Path C grep-verify across D1-D5 production + 2 mechanical scripts + AST invariant test files). **Bundle 4 closure-audit 2026-05-28 added 1 instance (34th)** — architect's independent Path C grep-verify caught 2 developer doctrine-arithmetic mis-attributions (§4.1 Per-artifact conflation + §4.2 Multi-discipline dropped-Bundle-3-instance), banking the Sub-rule 4 BIDIRECTIONAL-VALIDATION 4th instance (architect-catches-developer; completes 4-way matrix).

**Sub-rule 1 — MEMORY-FILE INDEX GAP family** (5+ instances; sub-rule elevation candidacy WARRANTED + ratified at P0.R10 closure-audit 2026-05-25):

Family of closure-narrative omissions where developer reports memory-file work complete but architect's Path C grep-verify catches a gap at MEMORY.md / memory-file path(s). Five sub-variants banked:

1. **MISSING-FILE** (P0.R6.Y closure-audit 2026-05-24) — developer claimed memory files landed but auto-memory path was empty; architect created files + added MEMORY.md index entries.
2. **MISSING-INDEX-ENTRY** (P0.R8 closure-audit 2026-05-25) — file landed but MEMORY.md index entry missing; architect added the missing entry.
3. **INDEX-CONTENT-STALE** (P0.R11 closure-audit 2026-05-25) — file extended correctly but MEMORY.md index entry content stale (didn't reflect new instance count / sub-shape extension).
4. **CROSS-PATH-SYNC-OMISSION** (P0.R11 closure-audit 2026-05-25, auditor-caught) — architect fixed gap at one memory path but missed propagation to parallel path; auditor's cross-path verification caught the omission. Cross-path sync invariant now formalized as operational discipline per `reference_architect_memory_path.md`.
5. **5th MISSING-INDEX-ENTRY** (P0.R10 closure-audit 2026-05-25) — architect-memory MEMORY.md missing entry for `feedback_auditor_precision_item_misframe.md` despite file landing at the path; architect closure-audit caught + fixed.

**Sibling gap class — DEFERRED-CANARY-ENTRY-OMISSION** (2 instances at P0.R10 closure-audit; same closure-claim-vs-artifact-reality drift shape but at `to_be_checked.md` surface instead of memory-file surface):

- 1st instance: P0.R8 closure (2026-05-24) — claim "deferred-canary entry pasted verbatim" but `to_be_checked.md` had zero matches.
- 2nd instance: P0.R9 closure (2026-05-25) — same claim, same gap.

**Sub-variant — STALE-CACHED-VERIFICATION** (bidirectional; 2 instances):
- 1st instance: P0.R9 Phase 0 verdict (2026-05-25) — auditor's verification claim based on session-start cached MEMORY.md state, NOT fresh Read; architect's fresh Read caught the stale cache + withdrew claim.
- 2nd instance: P0.R10 closure-audit fix-cycle (2026-05-25) — architect's Grep tool returned stale result for `to_be_checked.md`; developer's PowerShell fresh-disk read caught the stale cache + withdrew architect's catch.

Both instances validate the bidirectional grep-verify discipline. PowerShell fresh-disk read mechanism now locked at §6.4 of Plan v1 templates for `to_be_checked.md` verification.

**Sub-rule 2 — Multi-discipline preventive convergence** (3 instances at P0.R12-R15 Plan v1 verdict 2026-05-25; sub-rule elevation candidacy REACHED at 3-instance watch criteria per auditor banking):

When 5+ disciplines apply preventively in a single cycle (not catching real gaps; preventively-applied + auditor-verified clean), this signals operational floor stabilization. Three instances banked: P0.R10 (1st), P0.R12-R15 Phase 0 (2nd), P0.R12-R15 Plan v1 (3rd). Each instance applied 5+ disciplines including LINE-REF-DRIFT preventive + CODE-TEMPLATE-MISIDENTIFICATION preventive + CROSS-PATH-SYNC-OMISSION preventive commitment + DEFERRED-CANARY-ENTRY-OMISSION grep-verify commitment + closure-audit verdict forwarding commitment. Sub-rule elevation candidacy WARRANTED at next major architect-side narrative work.

**Sub-rule 3 — Closure-audit verdict cycle elision resolution** (2 cycles routinized at P0.R10 + P0.R12-R15):

Original concern at P0.R9: architect performed closure-audit internally without forwarding to auditor for explicit ratification verdict, breaking 4-step cycle integrity (Phase 0 verdict → Plan v1 verdict → closure-audit verdict → next-cycle Phase 0). Resolution locked at P0.R10 Plan v1 §9 procedural commitment + RATIFIED at P0.R10 closure-audit. 2nd cycle honoring (P0.R12-R15) — "procedural discipline becoming routinized" per auditor framing. The procedural gap is structurally resolved.

**Sub-rule 4 — BIDIRECTIONAL-VALIDATION cross-actor symmetry** (4 instances at Bundle 4 closure-audit 2026-05-28; ELEVATION EVENT LOCKED at Bundle 2 closure-audit at 3 instances; 4th instance completes the full 4-way cross-actor matrix):

The "architect reads production code" discipline is bidirectional — applies symmetrically to ALL three actors (architect, auditor, developer). When one actor's claim-vs-reality drift is caught by another actor's fresh grep-verify at named surface, the catching event banks under this sub-rule regardless of which actor performs which role.

**Four instances (3 at elevation 2026-05-28 + 4th at Bundle 4 closure-audit 2026-05-28):**

1. **P0.R9 architect-catches-auditor (STALE-CACHED-VERIFICATION sub-variant)** — auditor's Phase 0 verdict claimed pending CROSS-PATH-SYNC-OMISSION carry-forward was UNRESOLVED; architect's fresh Read at verdict-receipt time caught that the P0.R11 closure corrections HAD landed at the auditor-facing path. Auditor's verification was against session-start cached snapshot, NOT fresh Read at verdict time. Auditor withdrew carry-forward claim.

2. **Pre-P1 Bundle 1 Plan v2 developer-catches-architect (POWERSHELL-MEASUREMENT-ERROR sub-variant)** — architect's Phase 0 PowerShell `Get-Content | Measure-Object -Line` undercount mis-measured the source file by 42% (claimed 6487 lines on a 9214-line file; claimed 178 H2 sections vs actual 340). Developer's Pass-3 grep at Phase 4 pre-implementation caught the drift before code mutation. Architect owned the measurement error; Plan v2 absorbed via expanded cluster table 12 → 19 chapters covering §1-§340.

3. **Pre-P1 Bundle 2 Plan v2 auditor-catches-architect (VENDORED-MIT-IN-D6-SCOPE sub-variant; PI #3)** — architect's Plan v2 §2 D6 mechanical-script applied uniform `SPDX-License-Identifier: Apache-2.0` to all 204 in-scope files including 2 vendored MIT-licensed files (`core/_minifasnet/__init__.py` + `model.py`). Auditor's Plan v2 review caught the licensing-precision violation per REUSE Software spec semantics. Plan v3 absorbed via `EXCLUDED_PATHS = ("core/_minifasnet/",)` constant + Bundle 2.X concurrent MIT LICENSE file.

4. **Pre-P1 Bundle 4 closure-audit architect-catches-developer (DOCTRINE-ARITHMETIC-MISATTRIBUTION sub-variant)** — developer's Phase 4 closure narrative banked `Per-artifact-arithmetic-drift-survives-grep-baseline 18 → 19` with a collection-fan-out rationale (the 18→19 slot was already locked at the auditor's Plan v1 verdict for the Phase 0 PI #1 BEFORE-code drift) AND banked `Multi-discipline-preventive-convergence 9 → 10` (chronologically skipping Bundle 3's un-banked 10th instance). Architect's independent Path C grep-verify + doctrine track-record read at the closure surface caught both mis-attributions before banner corrections finalized. Auditor RATIFIED §4.1 (B) [Per-artifact STAYS 19 + `Plan-v2-collection-estimate-omits-AST-invariant-fan-out` 1→2] + §4.2 (A) [Multi-discipline 9→11; Bundle 3 retroactive 10th]. Auditor nuance for the record: §4.2's root cause is partly architect-catches-auditor (the Bundle 3 omission traced to the auditor's Bundle 3 closure verdict framing convergence as the trajectory metric), but the PROXIMATE catch (the developer's live 9→10 banking) is genuinely the new architect↔developer pair.

**Cross-actor symmetry validated** across 4 distinct actor pairs (the full matrix): architect-catches-auditor (P0.R9) + developer-catches-architect (Bundle 1) + auditor-catches-architect (Bundle 2) + architect-catches-developer (Bundle 4). The discipline's "grep-verify code-shape at named surface" property holds bidirectionally regardless of which actor performs the verification. Cross-actor independence + cross-cycle stability are the elevation criteria; the 4-way matrix completion is the maturity milestone.

**Falsification clause**: a future instance where the catching-actor's grep-verify was itself incorrect (e.g., catching-actor accuses producing-actor of drift but on re-verification the producing-actor's original claim was correct) would falsify the discipline. The load-bearing property is "fresh grep-verify catches what stale-cache verification misses"; falsification means a fresh grep produced a false-positive catch.

**Operational rules:**

1. **Path C grep-verify at closure surface**: closure-audit MUST grep-verify production code references + memory file landings (BOTH paths per cross-path discipline) + MEMORY.md index entries (BOTH paths) + `to_be_checked.md` deferred-canary entries (via PowerShell fresh-disk read, NOT Grep tool — per STALE-CACHED-VERIFICATION 2-instance lesson).
2. **Cross-path memory-file discipline**: when updating memory files, architect MUST verify BOTH the architect-memory path AND the auditor-facing memory path per `reference_architect_memory_path.md` line 10.
3. **Closure-audit verdict forwarding**: architect explicitly forwards closure-audit findings to auditor for ratification BEFORE declaring cycle CLOSED — preserves 4-step cycle integrity.
4. **Bidirectional grep-verify**: discipline applies to both actors. Architect's claim-vs-reality drift caught by auditor; auditor's stale-cache verification caught by architect's fresh Read.
5. **Multi-discipline preventive convergence is operational-floor evidence**: when 5+ disciplines apply preventively in a single cycle without catching gaps, document the convergence + bank as supporting evidence for operational floor stabilization.

**Future instances** continue to be banked under this doctrine's track record. Sub-rule elevation candidacies (MEMORY-FILE INDEX GAP family + Multi-discipline preventive convergence) lock at next major architect-side narrative work per the locked elevation procedure. The doctrine matures rather than re-elevating at higher thresholds.

> P0.R12-R15 closure-audit ratification 2026-05-25 + Bundle 2 closure-audit ratification 2026-05-28 banking: this doctrine text was extended at P0.R12-R15 closure-audit ratification per Option (a) — locks 4 sub-rule track records into canonical doctrine surface. **Bundle 2 closure-audit 2026-05-28 added Sub-rule 4 BIDIRECTIONAL-VALIDATION cross-actor symmetry** per 3-instance threshold reached (P0.R9 architect-catches-auditor + Bundle 1 developer-catches-architect + Bundle 2 auditor-catches-architect). Any future edit MUST preserve (a) the 4 sub-rule taxonomy headers (MEMORY-FILE INDEX GAP + Multi-discipline preventive convergence + Closure-audit verdict cycle elision resolution + BIDIRECTIONAL-VALIDATION cross-actor symmetry); (b) the bidirectional STALE-CACHED-VERIFICATION sub-variant; (c) the 5-instance MEMORY-FILE INDEX GAP enumeration; (d) the 4-instance BIDIRECTIONAL-VALIDATION enumeration with cross-actor pair labels (4-way matrix complete: architect↔auditor + developer↔architect + auditor↔architect + architect↔developer); (e) the operational rules block (5 rules including PowerShell fresh-disk read mechanism). Future CLAUDE.md compactions MUST NOT drift these anchors. Note: Sub-rule 2 (Multi-discipline preventive convergence) was simultaneously elevated to standalone `### Multi-discipline-preventive-convergence` numbered doctrine at Bundle 2 closure; track record stays here for cross-actor-verification framing context, AND the standalone doctrine carries the broader preventive-convergence framing.

### Twin-filename-pitfall-prevention

When a project has two same-named files at different paths serving different
roles, status-flip operations + closure artifacts MUST disambiguate explicitly
at artifact-creation time. Discovered at P0.S2 closure (developer flipped
status at subdir but missed parent path; architect's
`### Architect-reads-production-code-before-sign-off` discipline caught it).
Subsequent closures (P0.S3, P0.S4, P0.S6, P0.S7) applied the discipline
preventively + held the line.

**Track record (6 instances at P0.B1 closure):**
- **P0.S2 closure (2026-05-20):** 1st instance — gap-catch. Developer status-flip
  missed parent `complete-plan.md`. Architect closure-audit caught.
- **P0.S3 closure (2026-05-20):** 2nd — successful prevention via locked
  pre-flight checklist.
- **P0.S4 closure (2026-05-20):** 3rd — preventive application at audit drafting.
- **P0.S6 closure (2026-05-21):** 4th — preventive (intent-gates vs
  secrets-management P0.S6 disambiguation).
- **P0.S7 audit (2026-05-21):** 5th — preventive at audit drafting
  (`p0_s7_privacy_critical_*` vs prior P0.S7 D-A through D-E family arc).
- **P0.B1 closure (2026-05-21):** 6th — preventive at audit drafting (p0_b1_reconciler_hygiene_* clean against zero pre-existing P0.B artifacts; NEW Board-bug remediation track established with operational rule 4 + filename-prefix discipline locked at this closure).

**Operational rules:**
1. When ANY filename has parent/subdir or earlier-cycle/current-cycle twins,
   use distinguishing suffix at artifact creation time. NEVER rely on path
   alone to differentiate.
2. Closure pre-flight checklist (locked at P0.S2): verify status-flip at BOTH
   paths before declaring spec closed.
3. Architect closure-audit reads the actual files at BOTH paths; never trusts
   developer's narrative alone for the status flip.
4. **Bug-fix specs use `P0.B` prefix** (distinct from spec-track `P0.S` + resilience-track `P0.R`) + sub-name in filename (e.g., `p0_b1_reconciler_hygiene_*.md`). Same disambiguation discipline as spec-numbered cycles; locked at P0.B1 Phase 0 auditor adjudication 2026-05-21. The board-bug remediation track (10 bugs surfaced by skeptic1/skeptic2/ceo-evening meetings 2026-05-20/21) maps 1:1 to P0.B1-P0.B10.

**Why this matters:**

Same-name twin files are confusion clusters. The convention "use distinct
suffix at creation time" prevents the entire class of "I'll fix it later"
status-flip drift. P0.S2's gap-catch + the next 4 cycles' preventive
applications demonstrate the discipline working as designed.

**Falsification clause (locked at elevation, mirrors the other 3 elevated
doctrines):** if a future instance reveals the 5-instance threshold was
incorrectly counted (e.g., one of the 4 "preventive" applications wasn't
actually preventive, it was a false-positive flag), the doctrine demotes
back to architect-memory + the falsification banking applies.

**Future instances** continue to be banked. The discipline matures rather
than re-elevating at higher thresholds.

> P0.S7 Plan v2 §2.2 + Plan v1 §9 banking: this doctrine text is
> verbatim-sourced from Plan v1 §9 pre-draft (auditor-approved at Plan v2
> sign-off). Any future edit MUST preserve (a) the operational rules block
> (3 rules); (b) the "5 instances + discipline-stability evidence" framing
> as canonical narrative anchors; (c) the falsification clause. Future
> CLAUDE.md compactions MUST NOT drift these anchors.

### Phase-0-catches-wrong-premise

Every behavior-change P0/P1 cycle has a Phase 0 audit. The audit's job is
grep-verified findings BEFORE any code phase. 5 of 13 spec-first cycles
(P0.10, P0.S1, P0.S6, P0.S7, P0.S7.D-D) had their pre-audit mental model
falsified by Phase 0 grep — the architect's natural framing pointed at
the WRONG surface, and grep-verified evidence found the gap elsewhere.
At 5 instances, this pattern is now elevated to numbered doctrine:
expect Phase 0 to catch wrong-premise framing as a routine artifact, not
as a one-off discovery. When drafting a P0/P1 spec, treat the pre-audit
mental model as a hypothesis the audit will test — not as the locked scope.

**Discipline-stability evidence**: the architect held the strict-read
line across cycles that could have loose-counted to inflate the threshold
prematurely (P0.S7.2, P0.S7.D-C, P0.S7.D-B all explicitly NOT bumped despite
having borderline-elevation findings). That discipline-stability gives the
5th-instance lock its integrity.

**Operational rules:**
1. Phase 0 grep is the FIRST artifact, not the last. Frame the audit's job
   as "test my pre-audit hypothesis against grep evidence."
2. When Phase 0 falsifies the pre-audit premise, surface the reset
   explicitly — don't quietly proceed with the corrected scope.
3. Banking the falsification is the discipline working, not failing.

**Future instances** continue to be banked under this doctrine's track
record. The doctrine's instance enumeration grows as new examples
accumulate; no new memory-note creation needed. If discipline-stability
remains intact, the doctrine matures rather than requiring re-elevation
at higher thresholds (10+, 20+, etc.).

> P0.S7.D-D Plan v2 §5.4 LOW 1 banking: this doctrine text is
> verbatim-sourced from Plan v2 §5.1. Any future edit MUST preserve
> (a) the operational rules block (3 rules); (b) the "5 instances +
> discipline-stability evidence" framing as canonical narrative anchors;
> (c) the "future accumulation" clause. Future CLAUDE.md compactions or
> refactors MUST NOT drift these anchors.

### Verification-before-completion

When about to claim work is complete, fixed, or passing, before committing or creating PRs — run verification commands and confirm output before making any success claims. Evidence before assertions always.

**Full-suite closure-gate (banked at Pre-P1 Bundle 5 closure 2026-05-29).** Every spec closure MUST run the FULL test suite end-to-end with output shown — that run is the completeness proof. Anchor-test + incremental-subset verification + `pytest --collect-only` counts are NOT a substitute; they are bounded by their method. Bundle 3 + Bundle 4 declared "green full suite" from subset+collect-only verification without an independent full-suite run; Bundle 5's gate (the first full-suite run of the Pre-P1 arc) surfaced 2 latent Bundle-3 DEADLINE-MATH production bugs that shipped through both prior "green" closures (cache_store TTL clock-mismatch + pipeline.py:628 enrollment-rename WALLCLOCK). The hole spanned BOTH the architect's role (grep-verify production surfaces) AND the auditor's (same) — neither role included running pytest; the gate closes it for both, no blame assignment. Generalizes to the mature observation **`Full-suite-run-is-the-universal-completeness-proof`**: no static-verification claim (grep bounded by pattern+scope; anchor-subset bounded by not-full-run) should be asserted exhaustive beyond its method's actual coverage; the full-suite run, actually run, is the universal completeness proof. Sibling: `Full-suite-first-run-surfaces-prior-bundle-ripple` (a track-arc's first full-suite run surfaces latent prior-bundle ripple). The deepest lesson of the 5-bundle Pre-P1 arc.

### Phase-0-granular-decomposition-enables-accurate-estimates

Phase 0 audits that decompose the spec into concrete D-decisions with
named edit sites (`core/X.py:LINE`) produce auditor Q5 estimates that
land ON-TARGET (within tolerance). Phase 0 audits that aggregate into
high-level surface counts ("7 helpers," "3 components") produce
estimates that drift wildly in either direction.

**Track record (9 supporting instances + 3 contrary instances; SLIGHT-DRIFT readings NOT banked as supporting per strict ±15% ON-TARGET bar — locked at P0.S7 closure adjudication 2026-05-21):**

Supporting (decomposed → ON-TARGET):
- P0.S7.5 — 5 D-decisions × named edit sites → ON-TARGET (mid-range)
- P0.S7.5.1 — 1 D-decision × named edit site → ON-TARGET (+ Plan v2 defense-in-depth +1)
- P0.S7.5.2 — 5 D-decisions × named edit sites (multi-subsystem) → ON-TARGET (+ parametrize fan-out)
- P0.S2 — 7 D-decisions × named edit sites (cross-language) → ON-TARGET (non-DiD 18% within tolerance)
- P0.S3 — 2 D-decisions × named edit sites (5th supporting instance, locked at closure 2026-05-20; closure −10% UNDER upper bound)
- P0.S4 — 3 D-decisions × named edit sites (6th supporting instance — first post-elevation confirmation, locked at closure 2026-05-20; closure −20% UNDER upper bound; 2nd consecutive UNDER reading confirming Q5-B trajectory-reversal branch)
- P0.S5 — 3 D-decisions × named edit sites + first v1→v2→v3 spec iteration cycle. **NOT a supporting instance** (closure +22.2% vs mid-range = SLIGHT-DRIFT-UP per doctrine text's ±15-30% band → "watch trajectory" not supporting; bump initially claimed at closure 2026-05-21 but **rolled back at P0.S7 closure adjudication 2026-05-21** per strict-text alignment discipline. Within ±30% falsification tolerance, doctrine holds; 4-layer grep-verification discipline extension banked under separate sub-observation.)
- P0.S6 — 4 D-decisions × named edit sites (**7th supporting instance** — symmetric-over-estimate watch DEMOTED, locked at closure 2026-05-21; closure +5.5% vs mid-range ON-TARGET; trajectory bent back toward mid after P0.S5; bidirectional-drift framing of `Auditor-Q5-estimates-trail-grep` confirmed stable.)
- **P0.S7 — 4 D-decisions × named edit sites + AST tripwire suite. NOT a supporting instance** (closure −26.7% vs mid-range = SLIGHT-DRIFT-DOWN; first slight-UNDER reading after 4 cycles at-or-above-mid; bump initially claimed 8→9 in subdir narrative but **rolled back at P0.S7 closure adjudication 2026-05-21** per same strict-text alignment discipline as P0.S5. Within ±30% falsification tolerance, doctrine holds; bidirectional-drift framing CONFIRMED across 5 consecutive cycles spanning both slight-OVER and slight-UNDER directions — banked under `Auditor-Q5-estimates-trail-grep`, NOT as supporting instance.)

- **P0.B1 — 1 D-decision × named 15-site migration + AST tripwire (8th supporting instance — first FALSIFICATION-WATCH-ACTIVATED-then-DOWNGRADED-then-CONFIRMED instance under the doctrine; closure landed at 6 anchors vs auditor mid 6 = ON-TARGET 0%; locked at closure 2026-05-21 via architect closure-audit correction. Doctrine bumps from 7 → 8 supporting. Plan v2 §6 honest-count commitment honored at closure: closure-actual (6) BELOW Plan v2 lock (7) via further consolidation at impl time; architect closure-audit verified the 6-anchor count + applied doctrine bump per Plan v2 §2.5 projection (b).)**

- **P0.B2 — 5 D-decisions × named edit sites (`core/db.py:939-959` D1 + `:961-980` D2 + `:693-720` + `:1031-1091` D3+D4) + 3 behavioral D5 tests (fast-tier Test 3 + 2 slow-tier Tests 1+2) (9th supporting instance — closure landed at 10 anchors vs auditor mid 11 = ON-TARGET −9.1% per Plan v3 §1.1 corrected band table; locked at closure 2026-05-21. Doctrine bumps 8 → 9 supporting. Plan v2 §3 honest-count commitment HONORED — **4th instance of `Explicit-closure-honest-count-commitment` discipline**. v1→v2→v3 cadence driven by Plan v2 §3 band-arithmetic precision item (14-anchor row grouped ambiguously with falsification-trigger band) caught at Plan v3 P1 verdict — **2nd instance of `Auditor-catches-Q5-math-at-plan-review` informal observation**. HEAVY-band v1→v2→v3 cadence working hypothesis CONFIRMED — **2 instances banked** across distinct subsystems P0.S5 + P0.B2 [over-count "3rd instance" corrected to "2nd / 2 instances" at architect closure-audit 2026-05-21].)**

Contrary (aggregated → DRIFT):
- D-B — "8 surfaces" → HIGH 40%
- D-D — "7 helpers" → LOW 4×
- D-E — "single targeted helper" → LOW 60%

**Discipline-stability evidence:** the granularity correlation holds
across 4 scales (mini-spec ~3h, single-D-decision specs ~5h, 5-D-decision
specs ~9h, 7-D-decision multi-language specs ~12h) AND across multiple
subsystem counts (1, 5, 7). The correlation is independent of spec size
and subsystem fan-out.

**Sub-rule — `Doctrine-prediction-precision-improving-over-arc`** (RATIFIED at P0.R10 closure-audit 2026-05-25; 6+ consecutive 0%-streak rebuild instances at P0.R12-R15 closure):

When the granularity correlation produces 5+ consecutive exact-mid (0% drift) Q5 estimates across distinct cycles, this signals doctrine-prediction precision improvement over the cycle arc. Sub-observation extension WARRANTED at 5-instance threshold + RATIFIED at P0.R10 closure-audit per locked elevation procedure.

**Sub-rule track record (6 consecutive 0%-streak rebuild instances at P0.R12-R15 closure 2026-05-25):**

1. P0.R6.Z (2026-05-24) — 11 anchors at exact mid 11 = 0% drift; 1st 0%-streak rebuild
2. P0.R8 (2026-05-24) — 9 anchors at exact mid 9 = 0% drift; 2nd
3. P0.R11 (2026-05-25) — 9 anchors at exact mid 9 = 0% drift; 3rd
4. P0.R9 (2026-05-25) — 9 anchors at exact mid 9 = 0% drift; 4th
5. P0.R10 (2026-05-25) — 9 anchors at exact mid 9 = 0% drift; 5th — sub-observation extension WARRANTED; RATIFIED at this closure-audit
6. P0.R12-R15 (2026-05-25) — 9 anchors at exact mid 9 = 0% drift; 6th — additional supporting evidence

Pattern stability across diverse cycle scopes (heavy-worker watchdog / VRAM budget / crash diagnostics / audio device resilience / bundled-cycle hygiene). 6 consecutive cycles achieving closure-actual = exact mid-band of [7.65, 10.35] OR [3.4, 4.6] (NARROW band per Q5 spec). This is sustained empirical evidence the parent doctrine's "decomposed → ON-TARGET" correlation is tightening: not just within-tolerance, but at exact mid.

**Sub-rule falsification clause (locked at RATIFICATION):** if a future cycle with decomposed Phase 0 + named-edit-site granularity drifts ≥15% from mid (i.e., enters SLIGHT-DRIFT band), the streak breaks. Subsequent cycles must rebuild. If 2+ consecutive cycles drift ≥15%, sub-rule demotes back to architect-memory observation candidate.

**Operational rules:**
1. Phase 0 audits MUST decompose into explicit D-decisions with named
   edit sites at `core/X.py:LINE` granularity.
2. Aggregate framings ("7 helpers," "3 components") are rejected at
   Phase 0 review — re-decompose before locking the audit.
3. The improvement is incidental — the primary benefit of granular
   Phase 0 is for the developer reading the spec; downstream estimate
   accuracy is a side effect that nonetheless surfaces as a useful
   forecast signal.

**Future accumulation:** continue tracking. The doctrine matures
rather than re-elevating at higher thresholds. The contrary instances
(D-B / D-D / D-E) stay banked as falsification-resistance evidence —
if a future decomposed-Phase-0 instance drifts ≥30%, it FALSIFIES the
correlation and the doctrine demotes back to architect-memory.

> P0.S3 closure 2026-05-20 banking: this doctrine text is verbatim-
> sourced from `tests/p0_s3_audit.md` §8 pre-draft + auditor pre-approval
> at Phase 0 verdict. Any future edit MUST preserve (a) the operational
> rules block (3 rules); (b) the "5 supporting + 3 contrary" framing
> as the falsification-resistance anchor; (c) the falsification clause
> in the future-accumulation paragraph. Future CLAUDE.md compactions
> MUST NOT drift these anchors.

### Grep-baseline-before-drafting

Before drafting closure narratives or Plan v1/v2/v3 doctrine track-record updates,
grep-verify prior baseline counts from source-of-truth files. Stale-copy baselines
from much earlier closure narratives cause systematic +N/−N drift on discipline
counts; the only way to prevent this drift is to grep-verify against the most
recently ratified counts BEFORE writing.

**Track record (6 instances at elevation 2026-05-21):**

- **P0.B1 closure (2026-05-21):** 1st instance — architect closure-audit corrected
  stale-baseline drift (subdir "27 → 30" off-by-one → "31") via grep-verification.
  Convention-drift-on-discipline-counts 3rd instance banked simultaneously; the
  discipline was BORN at this closure as the prevention-side counterpart.
- **P0.B2 Phase 0 (2026-05-21):** 2nd instance — Phase 0 audit drafted from
  grep-verified baseline (audit-side preventive application).
- **P0.B2 Plan v2 §2 (2026-05-21):** 3rd instance — explicit baseline citation
  in closure-narrative paste-template (template-side preventive application).
- **P0.B3 Phase 0 (2026-05-21):** 4th instance — Phase 0 audit drafted from
  Post-P0.B2 ratified counts (cross-cycle-handoff preventive application).
- **P0.B3 Plan v1 (2026-05-21):** 5th instance — Plan v1 drafted from Phase 0
  + auditor Phase 0 verdict's locked counts (continued cross-cycle application;
  elevation candidacy reached).
- **P0.B3 closure (2026-05-21):** 6th instance — closure-narrative drafted
  from grep-verified Plan v1 §9 baseline counts; ELEVATION EVENT ratified per
  Plan v1 §12.3 architect closure-audit (4 verification criteria all passed).

**Discipline-stability evidence (auditor adjudication at P0.B3 Plan v1 verdict
2026-05-21 + closure-audit ratification 2026-05-21):**

The discipline was applied CONSISTENTLY across 6 consecutive applications without
silent drift. Cross-actor validation: auditor recommended at P0.B1 closure →
architect adopted → auditor's verdict-counts adopted at next-cycle Phase 0 →
no recurrence of stale-copy baseline drift. Working as intended.

**Operational rules:**

1. Before drafting closure narratives, grep `discipline-count: N`-style values
   in the most recently ratified source-of-truth files (CLAUDE.md + parent
   complete-plan.md + subdir complete-plan.md + memory-file track records).
   Cite the grep-verified baseline EXPLICITLY in the narrative + reference the
   source-of-truth file.
2. Before drafting Plan v1/v2/v3 doctrine track-record updates, perform the
   same grep-verify pass. Track-record additions MUST flow from grep-verified
   baseline, NOT from architect's working memory of "what the count was last
   time."
3. If a discrepancy surfaces between the grep-verified baseline AND the
   in-flight closure-narrative draft, the GREP wins. Auditor adjudication
   for the closure-actual count is the binding arbiter.

**Cross-disciplines (parent-child relationships):**

- `feedback_convention_drift_discipline_counts.md` (PARENT): closure-narrative
  count drift is the BASELINE drift class that this discipline prevents.
- `feedback_per_artifact_arithmetic_drift_survives_grep_baseline.md` (CHILD):
  the arithmetic drift class is OUT OF SCOPE for this discipline — grep-baseline
  catches BASELINE drift, not arithmetic drift. The CHILD observation tracks
  the gap.
- `### Phase-0-granular-decomposition-enables-accurate-estimates` (CLAUDE.md):
  symmetric counterpart on the estimation axis. Decomposed Phase 0 → narrow
  estimate; grep-verified baseline → accurate count.

**Falsification clause (locked at elevation, mirrors the other 3 elevated
doctrines — Phase-0-catches-wrong-premise + Twin-filename-pitfall-prevention +
Phase-0-granular-decomposition-enables-accurate-estimates):**

If a future instance reveals the 5-instance threshold was incorrectly counted
(e.g. one of the 5 "preventive" applications wasn't actually preventive, it was
a false-positive flag), the doctrine demotes back to architect-memory + the
falsification banking applies. Specifically: a closure where grep-baseline-
before-drafting WAS applied but Convention-drift drift STILL surfaced would
falsify the discipline (the prevention claim is the load-bearing property).

**Future instances** continue to be banked under this doctrine's track record.
The doctrine matures rather than re-elevating at higher thresholds.

> P0.B3 Plan v1 §12.1 banking: this doctrine text is verbatim-sourced from
> Plan v1 §12.1 pre-draft (auditor-approved at Plan v1 sign-off; closure-audit
> ratified at P0.B3 closure per §12.3 4-criteria verification). Any future
> edit MUST preserve (a) the operational rules block (3 rules); (b) the
> "5/6 instances + discipline-stability evidence" framing as canonical
> narrative anchors; (c) the cross-disciplines parent-child relationships;
> (d) the falsification clause. Future CLAUDE.md compactions MUST NOT drift
> these anchors.

### Zero-precision-items-at-auditor-review

When the architect-side artifact (Phase 0 audit OR Plan v1 OR Plan vN) lands
at auditor review with ZERO open precision items, this signals matured
discipline. The pattern represents the operational floor of the bug-fix arc:
clean cross-actor pre-emption, where architect proactively absorbs likely-
auditor-questions in the artifact itself + auditor cross-check finds zero
gaps.

**Track record (5 instances at elevation 2026-05-21):**

- **P0.B3 Plan v1 (2026-05-21):** 1st instance — Plan v1 absorbed 4 precision items.
- **P0.B5 Phase 0 (2026-05-21):** 2nd instance — Phase 0 premise ON-TARGET, 4 Qs to architect leans.
- **P0.B5 Plan v1 (2026-05-21):** 3rd instance — Plan v1 absorbed 4 items (FIRST MEDIUM-band OPTIONAL-Plan-v2).
- **P0.B6 Phase 0 (2026-05-21):** 4th instance — wrong-premise reframe + 2 new informal obs + 4 Qs to architect leans.
- **P0.B6 Plan v1 (2026-05-21):** 5th instance — Plan v1 absorbed 4 items + 4th OPTIONAL-Plan-v2 proof case + ELEVATION CANDIDACY REACHED.

**Discipline-stability evidence (auditor adjudication at P0.B6 Plan v1 verdict
2026-05-21):**

The discipline was applied CONSISTENTLY across 5 consecutive applications
without silent drift. Cross-actor validation: pattern co-discovered (architect
proactively absorbs anticipated items + auditor confirms via review with
explicit ACCEPT verdict on each instance).

**Operational rules:**

1. Before forwarding a Phase 0 audit or Plan v1 to auditor, architect MUST
   pre-empt the auditor's likely precision items proactively (multi-pattern
   Pass-2 grep + closure-template lock + AST tripwire shape + cross-spec
   impact + Q5 band-table + explicit open questions with architect leans).
2. The artifact's open-question section must surface ALL judgment calls that
   warrant adjudication, with explicit architect leans for each. Auditor's
   role becomes ratification, not gap-discovery.
3. When auditor returns 0 precision items, this is BANKING-EVIDENCE for the
   discipline — not a fluke; the artifact's quality + the pre-emption
   discipline are working in tandem.

**Structural relationship to `OPTIONAL-Plan-v2 path`:**

Zero-precision-items at Plan v1 review IS the trigger condition for
OPTIONAL-Plan-v2 path (skip Plan v2 + ship to developer). The two
disciplines describe the same operational floor from different angles:
Zero-precision-items names the AUDITOR-SIDE observation; OPTIONAL-Plan-v2
names the CYCLE-SHAPE consequence. Future consideration: may merge into
single doctrine at next major work if structural coupling holds.

**Cross-disciplines:**

- `### Phase-0-granular-decomposition-enables-accurate-estimates` (CLAUDE.md):
  upstream cause of clean Phase 0 reviews — granular decomposition produces
  narrow Q5 estimates AND pre-empts auditor questions.
- `### Grep-baseline-before-drafting` (CLAUDE.md): contributes to clean
  Plan v1 absorption by ensuring baseline counts are accurate before
  artifact draft.
- `feedback_bug_fix_cycles_surface_discipline_edges.md`: the bug-fix
  arc has been the discipline-growth engine that produced this elevation.

**Falsification clause (locked at elevation, mirrors the other 4 elevated
doctrines):**

If a future instance reveals the 5-instance threshold was incorrectly
counted (e.g., one of the 5 "instances" was actually a Plan v2 review
not a Phase 0/Plan v1 review), the doctrine demotes back to architect-
memory + the falsification banking applies. Specifically: a future
Phase 0/Plan v1 cycle where architect absorbed all anticipated items
but auditor STILL returned 1+ precision items would falsify the
discipline (the "matured discipline" claim is the load-bearing property).

**Future instances** continue to be banked under this doctrine's track
record. The doctrine matures rather than re-elevating at higher
thresholds.

**Sub-rule (absorbed at P0.S8 closure 2026-05-22 per architect's pre-closure
lean (b); auditor `Auditor-catches-doctrine-overlap-at-elevation-prep` 1st
instance resolved here at closure-time disposition):**

`Plan-v2-optional` (the cycle-shape consequence of zero-precision-items at
Plan v1 review) is formally absorbed as a sub-pattern under this doctrine
rather than elevated as a separate `### Plan-v2-optional` doctrine.
Rationale: structural coupling between the two descriptions is the same
operational floor from different angles — Zero-precision-items names the
AUDITOR-SIDE observation; OPTIONAL-Plan-v2 names the CYCLE-SHAPE consequence.
Per `feedback_auditor_catches_doctrine_overlap_at_elevation_prep.md`
(architect-side memory; auditor surfaced overlap concern at P0.S8 Plan v1
review), absorption avoids redundant doctrine surface while preserving the
empirical track record. The original 5-instance elevation anchor (per the
verbatim-lock notice below) remains intact; this sub-rule supplements it.

**OPTIONAL-Plan-v2 path proof cases (absorbed sub-pattern track record):**

- **P0.S3 (2026-05-20):** 1st proof case — small-spec band (2 D-decisions).
- **P0.B3 (2026-05-21):** 2nd proof case — small-spec band (2 D-decisions).
- **P0.B5 (2026-05-21):** 3rd proof case — FIRST MEDIUM-band cycle to clear
  (4 D-decisions across 4 subsystems).
- **P0.B6 (2026-05-21):** 4th proof case — small-band cycle (4 anchors).
- **P0.S8 (2026-05-22):** 5th proof case — small-band cycle (5 anchors);
  absorption event.

**Track record update (parent doctrine — counts both Phase 0 AND Plan v1
review instances per locked enumeration rule):** the 5 elevation instances
above continue as the canonical anchor per the verbatim-lock notice;
**P0.S8 contributes 2 separate instances — Phase 0 verdict (2026-05-22,
returned 0 precision items) adds as the 6th + Plan v1 verdict (2026-05-22,
returned 0 precision items) adds as the 7th**, while simultaneously serving
as the absorption event for the OPTIONAL-Plan-v2 sub-pattern.
Future instances bank under BOTH the parent count (zero-precision-items
applications) AND the sub-rule count (OPTIONAL-Plan-v2 path proof cases)
per the same instance enumeration. Falsification clause inherits from the
parent doctrine — a Phase-0 / Plan-v1 cycle where the architect absorbed
all anticipated items but auditor STILL returned 1+ precision items would
falsify BOTH the parent doctrine AND the sub-rule simultaneously.

> P0.B6 closure 2026-05-21 banking: this doctrine text is verbatim-sourced
> from `feedback_phase_0_zero_precision_items_at_auditor_review.md` Plan v1
> pre-draft (auditor-approved at Plan v1 verdict; closure-audit ratified at
> P0.B6 closure per 4-criteria verification — instance enumeration ✓ /
> discipline-stability ✓ / cross-reference integrity ✓ / falsification clause
> integrity ✓). Any future edit MUST preserve (a) the operational rules
> block (3 rules); (b) the "5 instances + discipline-stability evidence"
> framing; (c) the structural-relationship-to-OPTIONAL-Plan-v2 note; (d)
> the falsification clause. Future CLAUDE.md compactions MUST NOT drift
> these anchors.

### Canary-surfaces-real-gaps

Live multi-person canaries are a structural test of the cognitive
runtime against realistic usage. They reliably surface gaps that
spec-time grep + Phase 0 audit cannot reach — bugs that only
manifest under composed real-world conditions (timing, multi-pid
interaction, model non-determinism, hardware variation). Canary-
surfaced gaps are treated as REAL architectural findings, not as
canary noise. 5 of the spec-cycles after the P0.S7 family ship
crossed this threshold — the doctrine is now numbered.

**Track record (batting 5-for-5):**
- **P0.S7.2** — Cross-session memory retrieval gap. 2026-05-18
  canary: Jagan returned to fresh session, asked about cheese
  cookies recipe from prior multi-person room, brain confidently
  denied. Two-part fix surfaced (γ prompt + κ extraction).
- **P0.S7.3** — KAIROS silence-baseline. Live canary surfaced
  KAIROS firing immediately after a 3-minute TTS playback:
  pre-fix `_silence_elapsed = now - _last_user_speech_at`
  accumulated silence DURING brain-speaking time, so long TTS
  made the silence threshold trip the moment TTS ended — no
  breathing room. Fix: silence-baseline =
  `max(last_user_speech_at, _tts_end_time)`; brain-speaking time
  no longer counts as silence.
- **P0.S7.5** — Bundled-queue canary 2026-05-19 cluster: visitor
  alert nudge one-shot consumed before owner asked; VISITOR CONTEXT
  block didn't fire; brain confabulated "No one was here." 5
  D-decisions shipped.
- **P0.S7.5.1** — Canary 2 (2026-05-19) marker/metadata asymmetry:
  `_run_visitor_alert` writes `[visitor_name:unknown]` but metadata
  has `visitor_name="visitor"`; `update_visitor_alert_for_promoted_
  person` literal-substring replace silently no-op'd. Single
  D-decision lambda-replacement fix.
- **P0.S7.5.2** — Canary 3 (2026-05-20) multi-subsystem cluster:
  5 independent root causes across reconciler / pipeline / voice
  gallery / audio / brain prompt-blocks. 5 D-decisions shipped.

**Discipline-stability evidence:**

The architect held the strict-read line across non-canary cycles
that could have inflated the count prematurely (P0.S7.D-B was
deferral-rationale-expires, not canary; P0.S7.D-D was wrong-premise,
not canary; P0.S7.D-E was partial-falsification, not canary). That
discipline-stability gives the 5th-instance lock its integrity —
matches the `### Phase-0-catches-wrong-premise` elevation cadence.

**Operational rules:**

1. **Canary findings are real, not noise.** When a live canary
   surfaces a behavior gap, file a follow-up spec under strict
   mode. Don't dismiss canary failures as "model non-determinism"
   without grep-verified root-cause investigation.
2. **Multi-agent parallel investigation for multi-subsystem
   failures.** When a canary surfaces failures spanning ≥3
   subsystems, dispatch parallel investigation agents (per
   `feedback_strict_industry_standard_mode.md` §1 pre-mortem
   discipline). Synthesize findings into a single Phase 0 audit.
3. **Production-canary diff at closure.** Every canary
   terminal_output.md gets diffed against the prior canary as
   part of closure-narrative banking. Distinguish "new failure
   mode" from "regression" from "same failure" — different
   responses.

**Future accumulation:**

Future canary-surfaced instances continue to be banked under
this doctrine. The instance enumeration grows as new examples
accumulate; no new memory-note creation needed. If discipline-
stability remains intact, the doctrine matures rather than
requiring re-elevation at higher thresholds.

> P0.S7.5.2 Plan v2 §7 banking: this doctrine text is verbatim-
> sourced from Plan v2. Any future edit MUST preserve (a) the
> operational rules block (3 rules); (b) the "5 instances +
> discipline-stability evidence" framing; (c) the multi-agent
> parallel investigation rule (P0.S7.5.2-specific addition);
> (d) the production-canary diff rule. Future CLAUDE.md
> compactions MUST NOT drift these anchors.

### Pass-2-grep-auditor-verified-before-Plan-v1-approval

Pass-2 grep at Plan v1 drafting time MUST be performed by both architect
(at draft time) AND auditor (at Plan v1 review). The architect's Pass-2
enumeration catches drift between Phase 0 §1 Pass-1 baseline and Plan v1
§1 implementation scope; the auditor's Pass-2 verification catches drift
within Plan v1 itself (contract vs implementation, file vs file,
enumeration vs reality). Two independent passes at the same surface +
convergence on findings = preventive discipline working at the operational
floor of Plan v1 review.

**Track record (5 applications + 4-criteria adjudication ratified at
P0.R4 closure-audit 2026-05-23):**

- **P0.R2 Plan v1 (2026-05-23):** 1st application — clean cycle. Auditor's
  Pass-2 grep returned 0 precision items because architect's Pass-2 grep
  at draft time already caught everything.
- **P0.R3 Phase 0 (2026-05-23):** 2nd application — clean. Pattern-broken
  streak begins (Phase 0 + Plan v1 reviews returning 0 PIs consecutively).
- **P0.R3 Plan v1 (2026-05-23):** 3rd application — clean. 3-consecutive-
  cycle empirical validation reached → rule PROMOTED to FORMAL RULE STATUS
  under `feedback_spec_time_grep_verification.md`.
- **P0.R4 Phase 0 (2026-05-23):** 4th application — clean. 4th consecutive
  pattern-broken-streak cycle.
- **P0.R4 Plan v1 (2026-05-23):** 5th application — **caught real gap**.
  Plan v1 §1.2 enumerated D4 contract as "all `os.getenv(...)` keys
  documented" but listed only TOGETHER_API_KEY + HF_TOKEN; auditor's Pass-2
  grep surfaced PI #1 (D4 enumeration drift — missing GROQ_API_KEY +
  TAVILY_API_KEY from contract-vs-implementation enumeration). Pattern-
  broken streak INTERRUPTED at 4. Doctrine's catching mechanism actively
  validated.

**Both validation modes** prove the rule's preventive purpose: the 4 clean
cycles validate ABSENCE of drift (no PI surfaces because both passes
converge on the same findings, indicating discipline operating correctly);
the 1 caught-real-gap cycle validates PRESENCE of catching (PI surfaces
because architect's pass missed a real drift, and auditor's pass catches
it). Convergence is the cross-actor signal; divergence (PI surfaces) is
the catching event. Either outcome validates the rule.

**Discipline-stability evidence:**

- 0 silent rollbacks across 5 applications
- 0 false-positive flags (every PI surfaced corresponded to a real
  enumeration miss)
- Cross-actor validation (architect + auditor both perform Pass-2 grep
  at independent surfaces; convergence on findings demonstrates
  discipline-stability, divergence demonstrates catching)
- Rule operates ACROSS cycle shapes — code-change cycles (P0.R2/R3
  cognitive runtime supervision) + deployment-artifact cycles (P0.R4 NEW
  artifacts only, zero Python production code changes) BOTH exercise the
  rule effectively

**Operational rules:**

1. Architect's Pass-2 grep at Plan v1 §1 drafting MUST enumerate all
   surfaces touched per the Phase 0 §1 baseline + all D-decisions; output
   goes into Plan v1 §1.2 enumeration table verbatim.
2. Auditor's Pass-2 verification at Plan v1 review MUST cross-grep the
   same surfaces independently; convergence → no PI; divergence → PI
   surfaces with explicit "Plan v1 §1.2 enumeration drift" rationale.
3. PI surfacing at auditor Plan v1 verdict ROUTES through OPTIONAL-Plan-v2
   path (cycle escalates from v1-direct-to-developer to v1→v2 absorption).
   Per `Plan-v1-Pass-2-grep-undercount` informal observation, the
   absorption pattern is itself a banked discipline shape.
4. When the rule catches a real gap, the Plan v2 absorption MUST encode
   structural enforcement at the test surface to prevent regression of
   the catching mechanism (P0.R4 §2.5 A8 programmatic enforcement is the
   canonical pattern — replaces hardcoded enumeration with regex-extracted
   programmatic enforcement so future surface additions are automatically
   caught at CI).

**Cross-disciplines (parent-child relationships):**

- **Parent (upstream)**: `### Grep-baseline-before-drafting` — the
  baseline-establishment discipline that Pass-2 grep at Plan v1 draft
  time builds upon. Architect's Pass-2 grep IS the Plan-v1-side application
  of the Grep-baseline discipline.
- **Parent (upstream)**: `### Phase-0-granular-decomposition-enables-
  accurate-estimates` — D-decision granularity at Phase 0 supports
  comprehensive Pass-2 enumeration at Plan v1. Aggregated Phase 0
  framings make Pass-2 grep brittle.
- **Child (downstream observation)**: `Plan-v1-Pass-2-grep-undercount` —
  the failure-mode tracker for Pass-2 enumeration misses. The 6 instances
  banked at this discipline ARE the catching events that validate the
  Pass-2-grep-auditor-verified rule.
- **Sibling**: `### Zero-precision-items-at-auditor-review` — same
  operational floor from different angles. Zero-precision-items names the
  AUDITOR-SIDE outcome observation across Phase 0 + Plan v1 + Plan v2
  reviews; Pass-2-grep-auditor-verified names the SPECIFIC MECHANISM
  (cross-actor grep at Plan v1 surface) that produces the clean outcomes
  AND the caught-gap outcomes. The two doctrines together describe the
  why + the how of Plan v1 review discipline maturity.

**Falsification clause (locked at elevation, mirrors the other 6
elevated doctrines):**

If a future cycle where architect's Pass-2 grep at Plan v1 drafting
PASSED CLEANLY (no enumeration drift surfaced at draft time) AND
auditor's Pass-2 grep at Plan v1 review STILL surfaced a Plan-v1
enumeration undercount that the architect could have caught with a
proper Pass-2 enumeration, the doctrine demotes back to architect-memory
+ falsification banking applies. The load-bearing property is that
"auditor cross-check catches what architect's discipline misses" —
falsification means both passes converged on a clean result that turned
out to be wrong (i.e., neither actor caught a real drift that surfaced
later at Plan v2 absorption OR closure-audit OR developer Phase 5
implementation).

**Future instances** continue to be banked under this doctrine's track
record. The doctrine matures rather than re-elevating at higher
thresholds.

> P0.R4 closure-audit 2026-05-23 banking: this doctrine text is verbatim-
> sourced from Plan v2 §5.1 pre-draft (architect closure-audit ratified
> at P0.R4 closure per 4-criteria verification — instance enumeration ✓ /
> discipline-stability ✓ / cross-reference integrity ✓ / falsification
> clause integrity ✓). Any future edit MUST preserve (a) the operational
> rules block (4 rules); (b) the "5 applications + 4 clean + 1 caught-
> real-gap" framing as the load-bearing track record; (c) the both-
> validation-modes argument (clean cycles validate ABSENCE, caught
> cycles validate PRESENCE); (d) the cross-disciplines parent-child
> relationships; (e) the falsification clause. Future CLAUDE.md
> compactions MUST NOT drift these anchors.

### Pre-audit-quantifier-precision-refined-by-grep

Pre-audit framings of a spec's scope commonly use quantifier-precision
APPROXIMATIONS (rough counts, abstract mechanism descriptors, generic
infrastructure terms) that grep-verification at Phase 0 drafting time
refines toward precise values. These refinements are NOT pre-audit
errors — they're the discipline working: the pre-audit captures
problem-shape; Phase 0 grep captures problem-scale. Multi-axis sub-shape
taxonomy emerges organically as the pattern recurs across cycles.

**Track record (8 applications + 8-axis sub-shape taxonomy; extended at
P0.R6.Z closure-audit 2026-05-24 per Plan v1 §10 item 5 + reviewer's
Observation 1 resolution [8-axis enumeration chosen, counting
LAYERED-AXIS-continuation as a distinct axis]):**

- **P0.B3 D-D Phase 0 (2026-05-21):** 1st application — **COUNT-axis**
  sub-shape. Pre-audit "refactor 50+ `_active_sessions[pid]` access
  sites — 5-7 days" framing refined by Phase 0 grep to "0 remaining
  sites; actual scope is 7 module-level helpers; ~1 to 1.5 days." Banked
  as `feedback_pre_audit_quantifier_precision_refined_by_grep.md` 1st.
- **P0.R2 §2.6(b) Phase 0 (2026-05-23):** 2nd application —
  **MECHANISM-AXIS** sub-shape. Pre-audit "no CPU fallback path"
  overstated; Phase 0 grep verified 1/3 sites already had lazy fallback
  post-P0.R1.
- **P0.R4 Q3 Phase 0 (2026-05-23):** 3rd application —
  **MECHANISM-GENERALITY-AXIS** sub-shape. Pre-audit "exponential
  backoff" precise for supervisord; approximate for systemd which uses
  bounded burst limit. Phase 0 grep refined to "spec contract uniform
  across supervisors via different native mechanisms."
- **P0.R5 Phase 0 (2026-05-23):** 4th application — **LAYERED-AXIS**
  sub-shape (3 simultaneous axes at single Phase 0 surface):
  DEP-INFRASTRUCTURE-AXIS via Q1 (pre-audit "pyproject.toml" framing
  refined to `requirements.txt` git URL syntax) + SCOPE-AXIS via Q3
  (pre-audit "pyannote only" refined to BOTH pyannote + speechbrain) +
  DEP-PINNING-AXIS via Q7 (pre-audit "concrete SHA at Plan v1
  drafting" refined to placeholder `@<SHA>` option (α) syntax).
- **P0.R6 Phase 0 (2026-05-24):** 5th application — **LAYERED-AXIS
  continuation** (2-axis): TASK-COMPLETENESS-AXIS via Q1 (pre-audit
  "single P0.R6 ships all 4 task migrations" refined to Q1 (a)
  decomposition — P0.R6 foundation + AdaFace; P0.R6.X-Z subsequent
  specs for Whisper + ECAPA + pyannote) + SCALE-OF-WORK-AXIS via D3
  Plan v1 PI #1 absorption (pre-audit "2 AdaFace async-hot-path sites"
  refined by auditor independent re-grep to 4 — sites 6716 + 7112
  were SYNC DIRECT CALLS blocking the asyncio loop, NET-NEW
  non-blocking improvements). **5-instance elevation threshold reached
  → doctrine ELEVATED at P0.R6 closure-audit per locked precedent.**
- **P0.R6.X Phase 0 (2026-05-24):** 6th application —
  **TASK-COMPLETENESS-AXIS** continuation. Pre-audit "~2-3 sites"
  framing refined by Phase 0 grep to "1 inference site" (Whisper has a
  single `model.transcribe(...)` call in `core/audio.py::transcribe()`
  body; everything else is filter-chain). 1st post-elevation firing
  validates the doctrine's catching mechanism extends past the
  elevation event.
- **P0.R6.Y (2026-05-24):** 7th application — **SURFACE-CASCADE-AXIS**
  NEW sub-shape. Pre-audit Phase 0 framing of "4 patch sites in
  `test_pipeline.py`" (architect Pass-1 grep) cascaded through 5 rounds
  of bidirectional grep iteration to converge at 38 sites across 4 API
  shapes × 6 test files. Pass-1: 4 sites. Pass-2 (auditor at Plan v1
  verdict): 13 sites (PI #1; missed 9 sites within Shape A).
  Pass-3 (architect at Plan v2): 19 sites (auditor's off-by-one
  corrected to 12 + 3 NEW API shapes Shape B + C + D surfaced).
  Pass-4 (auditor at Plan v2 verdict): 33 sites (PI #2; architect-
  side undercount on Shape C across 4 test files + Shape D 7 diarize
  calls). Pass-5 (architect at Plan v3): 38 sites (auditor-side
  undercount on Shape C `_vs` alias 4 sites + Shape D
  `_diarize_ecapa_valley` 1 site). Pass-6 (architect at closure-
  narrative drafting): site #39 surfaced (test_diarize_returns_empty_
  when_audio_too_short at test_pipeline.py:6422 missed by Pass-5)
  banked as `Plan-v1-Pass-2-grep-undercount` 10 → 11 instance per
  reviewer's Phase 5 banking watch. Sub-shape distinct from prior 6
  axes — surfaces the multi-round CASCADE dynamic where each grep
  pass refines BOTH count AND structural coverage (new API shapes /
  new file scopes / new aliases). Cross-references the parallel
  `feedback_iterative_bidirectional_catching_convergence.md`
  architect-memory observation NEW-banked at this closure (first 5+
  round bidirectional iteration on the same enumeration drift).
- **P0.R6.Z (2026-05-24):** 8th application — **RETIREMENT-SURFACE-AXIS**
  NEW sub-shape. Pre-audit framing "2 surfaces" (pipeline migrate +
  executor retire) refined by Phase 0 grep to **23 distinct retirement
  events**: 5 production surfaces in `core/voice.py`
  (`_voice_diarize_executor` + `get_diarize_executor` +
  `shutdown_diarize_executor` + `_pyannote_pipeline` +
  `_load_pyannote_pipeline` — all HARD-DELETE per Q1 (a) lock) + 4
  `pipeline.py` surfaces (`_warm_pyannote_via_dedicated_executor`
  function + 2 call sites + `shutdown_diarize_executor` call) + 14 test
  surfaces (6 Shape B `patch.object` migrations + 6 Shape C stub
  retirements + 7 obsolete test methods retired/repurposed). Structurally
  distinct from prior 7 axes (COUNT / MECHANISM / MECHANISM-GENERALITY /
  LAYERED / LAYERED-CONTINUATION / TASK-COMPLETENESS / SURFACE-CASCADE)
  — captures orthogonal RETIREMENT SCOPE dimension under-weighted by
  the "retire X + add Y" pre-audit framing. The sub-shape surfaces a
  general failure mode: pre-audit framings tend to count NEW surfaces
  + ADDITIONS but under-count RETIREMENT scope when the migration
  pattern is "replace X with Y" — the X-side surface count is
  systematically smaller in pre-audit than at Phase 0 grep verification
  time. 2nd post-elevation firing of the doctrine validates the
  catching mechanism continues to extend post-elevation. 4-task
  heavy-worker migration arc COMPLETES at this instance (AdaFace P0.R6
  + Whisper P0.R6.X + ECAPA P0.R6.Y + Pyannote P0.R6.Z = full cognitive
  runtime asyncio-loop-release).

**Discipline-stability evidence:**

- 8 consecutive cycles' pre-audit framings refined at Phase 0 grep
  verification time without silent rollback OR re-introduction of the
  imprecise values at subsequent artifact drafting.
- Cross-actor independence — architect drafts pre-audit; Phase 0 audit
  applies grep; auditor cross-verifies at Plan v1 verdict. Refinements
  surface at each layer rather than concentrating at one actor.
- Sub-shape taxonomy grew organically across the 8 applications:
  COUNT-axis → MECHANISM-AXIS → MECHANISM-GENERALITY-AXIS →
  LAYERED-AXIS (multi-axis at single Phase 0 surface) →
  LAYERED-AXIS-continuation → TASK-COMPLETENESS-AXIS →
  SURFACE-CASCADE-AXIS (multi-round bidirectional grep iteration
  refines BOTH count AND structural coverage; P0.R6.Y 5-round
  convergence on test infrastructure migration) →
  RETIREMENT-SURFACE-AXIS (orthogonal RETIREMENT scope dimension
  under-weighted by "retire X + add Y" pre-audit framing; P0.R6.Z 23
  retirement events refined from "2 surfaces" pre-audit). Each
  instance contributed a distinct failure-mode shape; the doctrine's
  instance enumeration captures this taxonomy rather than collapsing
  all instances under one shape.

**Operational rules:**

1. Pre-audit framings MAY use quantifier-precision approximations
   ("~5 sites," "around 50 callers," "exponential backoff," "all
   AdaFace sites") — these are problem-shape captures, not
   commitments. Phase 0 grep refines to precise values.
2. Phase 0 audit MUST grep-verify every quantifier in the pre-audit
   framing. Refinement events are first-class artifacts — log them
   in Phase 0 §1 (grep findings) with explicit pre-audit-vs-grep
   delta + sub-shape classification.
3. If Phase 0 grep CONFIRMS the pre-audit framing (no refinement
   needed), no instance bank fires. Refinement events bank an
   instance ONLY when grep surfaces a precision delta.
4. When the same axis (COUNT, MECHANISM, SCOPE, etc.) recurs across
   instances, bank them as continuations of the same sub-shape rather
   than as new sub-shapes. Sub-shape taxonomy grows when a genuinely
   NEW failure-mode dimension surfaces.

**Cross-disciplines:**

- **Parent (upstream)**: `### Grep-baseline-before-drafting` — Phase 0
  grep verification IS the discipline that catches pre-audit
  quantifier-precision approximations. This doctrine names the
  refinement EVENTS that the parent discipline produces.
- **Parent (upstream)**: `### Phase-0-catches-wrong-premise` — wrong-
  premise is the SUBSTANTIVE counterpart (pre-audit's mental model of
  THE PROBLEM was wrong); this doctrine is the QUANTITATIVE
  counterpart (pre-audit's mental model of PROBLEM-SCALE was
  approximate). Both surface at Phase 0 grep; both validate the
  spec-first discipline.
- **Sibling**: `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` —
  the auditor-side Pass-2 grep at Plan v1 review is the cross-actor
  cross-check that catches Phase-0-side refinements the architect's
  initial pass missed (P0.R6 PI #1 D3 enumeration drift was the
  canonical example — architect's Phase 0 said "2 AdaFace async
  sites," auditor's Plan v1 Pass-2 grep refined to 4).

**Falsification clause (locked at elevation, mirrors the other 7
elevated doctrines):**

If a future cycle where the pre-audit framing was QUANTITATIVELY
PRECISE (Phase 0 grep CONFIRMS pre-audit values; no refinement
event) STILL surfaced a precision item at the architect closure-audit
that the Phase 0 grep should have caught, the doctrine demotes back to
architect-memory + falsification banking applies. Specifically: a Phase
0 audit that grep-verified the pre-audit framing as precise but later
turned out to have missed a real quantifier refinement (the missed
refinement surfaces only at Plan v1 review OR developer Phase 5 OR
closure-audit) would falsify the doctrine — the "Phase 0 grep catches
pre-audit quantifier approximations" property is the load-bearing
claim.

**Future instances** continue to be banked under this doctrine's track
record. Sub-shape taxonomy may grow as new failure-mode dimensions
surface. Doctrine matures rather than re-elevating at higher
thresholds.

> P0.R6 closure-audit 2026-05-24 banking: this doctrine text is
> verbatim-sourced from auditor's Phase 0 verdict 2026-05-24 proposed
> body + Plan v1 §1.4 elevation-candidacy reasoning. Any future edit
> MUST preserve (a) the operational rules block (4 rules); (b) the
> "5 applications + 4-axis sub-shape taxonomy" framing as the
> load-bearing track record; (c) the parent-sibling cross-disciplines
> structure; (d) the falsification clause. Future CLAUDE.md
> compactions MUST NOT drift these anchors.

### Resilience-track-arc-completion

When a multi-cycle P0.X-prefix technical track concludes with comprehensive architectural coverage across distinct failure-mode dimensions, document the arc-completion as an explicit milestone. The milestone is bank-worthy when (a) the cumulative cycles form a coherent architectural arc covering a complete capability dimension; (b) each cycle's closure narrative is independently complete + auditor-ratified; (c) the arc's last numbered cycle closes with the same procedural discipline as earlier cycles in the arc.

**Track record (2 instances; 2nd advances the elevation candidacy 2026-05-29):**

- **P0.R arc completion (2026-05-25 at P0.R12-R15 closure):** 14-cycle resilience-track arc COMPLETE — P0.R1 + R2 + R3 + R4 + R5 + R6.* (foundation + X + Y + Z) + R8 + R9 + R10 + R11 + R12 + R13 + R14 + R15. P0.R7 DEFERRED per user's plans. Cognitive runtime resilience surface now spans 10 numbered recovery capabilities: ONNX session.run wrap + Proactive CPU-EP fallback + Vision-loop watchdog + Process supervisor + Vendored pyannote + Heavy-task worker foundation + 4 task migrations + Heavy-worker pool watchdog + VRAM budget guard + Audio device resilience + Crash diagnostic capture + Conversation_log_archive retention + terminal_output.md size cap + rotation + Camera index AST invariant + time.sleep async AST invariant. NEW `feedback_resilience_track_arc_completion.md` banked at BOTH memory paths.

- **Pre-P1 must-fix arc completion (2026-05-29 at Bundle 5 closure):** 5-bundle Pre-P1 arc COMPLETE — Bundle 1 (Docs+CI MF1+MF3+MF10) + Bundle 2 (Governance MF2) + Bundle 3 (Critical-bugs MF4+MF5) + Bundle 4 (Observability+Concurrency MF6+MF9) + Bundle 5 (Contract-typing MF7+MF8). **2nd arc-completion milestone across a distinct track** (sibling to the P0.R resilience arc). Per the sub-rule elevation criteria (2+ arc-completion milestones across distinct tracks + cross-actor auditor ratification + discipline-stability), this 2nd instance advances `### Resilience-track-arc-completion` toward elevation to the broader `### Architectural-arc-completion-milestone-banking` doctrine. The arc's final bundle earned its keep: its full-suite closure-gate caught 2 latent Bundle-3 production bugs that had shipped through 2 prior "green" closures, and banked the arc's deepest lesson — `Full-suite-run-is-the-universal-completeness-proof`. Next: P1 cycle (8-10 week clock, 5 parallel tracks).

**Why this matters:**

Arc-completion milestones differ from per-cycle closures in 3 ways:
1. **Architectural coverage signal**: the arc's cumulative scope spans a complete capability dimension (cognitive runtime resilience in P0.R's case). Individual cycles are partial coverage; the arc's last cycle is the completion event.
2. **Doctrine maturation evidence**: arc-completion typically coincides with multi-discipline preventive convergence + sub-rule elevation candidacies (P0.R12-R15 closed with 3 sub-rule elevation candidacies + 6th consecutive 0%-streak rebuild). The arc's procedural discipline has matured to the point that downstream cycles require less rework.
3. **Forward-looking anchor**: future cycles in the same dimension (resilience hygiene follow-ups, etc.) reference the arc as the locked baseline; new resilience work either extends the arc OR justifies why it doesn't fit the arc's structural assumptions.

**Sub-rule elevation criteria** (per locked elevation procedure at 4-criteria check):

- 2+ arc-completion milestones across distinct P0.X-prefix tracks (different capability dimensions)
- Cross-actor validation: auditor RATIFIES the arc-completion milestone at the last cycle's closure-audit
- Discipline-stability evidence: no silent rollbacks across the arc's cycles
- Falsification clause: if a future "arc-completion" milestone is later revealed as incomplete (e.g., a deferred sub-scope from one of the arc's cycles surfaces a real gap that requires opening a new cycle in the arc), the milestone demotes back to "arc-mostly-complete" + the gap-resolution cycle joins the arc.

**Operational rules:**

1. When a P0.X-prefix track's last numbered cycle closes, evaluate if the cumulative cycles form an architectural arc per the 3 "why this matters" criteria.
2. If yes, document the milestone with explicit cycle enumeration + capability-dimension framing in BOTH the closure narrative AND a dedicated memory file.
3. Cross-path discipline applies: arc-completion memory file lands at BOTH memory paths + MEMORY.md index entries at BOTH paths.
4. Bank as architect-memory doctrine candidate at 1st instance; sub-rule elevation candidacy WARRANTED at 2nd instance + 4-criteria check.

**Future instances** continue to be banked under this doctrine's track record. Watch criteria: 2+ arc-completion milestones may elevate to formal sub-rule under appropriate parent doctrine (likely `### Spec-first review cycle for multi-day specs` since arc-completion is the integral of multi-cycle spec-first discipline).

> P0.R12-R15 closure-audit ratification 2026-05-25 banking: this doctrine text is verbatim-sourced from auditor's P0.R12-R15 closure-audit verdict (proposed banking of `### Resilience-track-arc-completion` doctrine candidate) + architect's `feedback_resilience_track_arc_completion.md` 1st instance banking. Any future edit MUST preserve (a) the 3 "why this matters" criteria; (b) the 14-cycle P0.R arc enumeration in the track record; (c) the sub-rule elevation criteria + falsification clause; (d) the operational rules block (4 rules). Future CLAUDE.md compactions MUST NOT drift these anchors.

### Multi-discipline-preventive-convergence

When 5+ disciplines apply preventively in a single cycle (catching no real gaps; preventively-applied + auditor-verified clean), this signals operational floor stabilization. Distinct from catching-mode disciplines — preventive convergence is evidence that the project's quality machinery has matured to the point that multiple disciplines fire as routine artifacts rather than as gap-catches. Cross-cycle preventive trajectories (5 → 6 → 7 → 8 → 9 disciplines per cycle) are the load-bearing pattern; single-cycle high counts without trajectory context are coincidence.

**Track record (11 instances; 9 at elevation 2026-05-28 + Bundle 3/Bundle 4 retroactive corrections at Bundle 4 closure-audit §4.2 (A) ratification 2026-05-28):**

- **P0.R10 closure (2026-05-25)** — 1st instance. 5 disciplines: LINE-REF-DRIFT preventive + CODE-TEMPLATE-MISIDENTIFICATION preventive + CROSS-PATH-SYNC-OMISSION preventive commitment + DEFERRED-CANARY-ENTRY-OMISSION grep-verify commitment + closure-audit verdict forwarding commitment.
- **P0.R12-R15 Phase 0 (2026-05-25)** — 2nd. Same 5 disciplines.
- **P0.R12-R15 Plan v1 (2026-05-25)** — 3rd. Same 5 + auditor pre-ratification.
- **P0.S11 (2026-05-27)** — 4th. 5+ disciplines preserved at closure.
- **P0.S12 (2026-05-27)** — 5th. 5+ disciplines + in-cycle A1 strengthening.
- **P0.S10 (2026-05-27)** — 6th. 7 disciplines preventively applied per Plan v2 §5.4 enumeration including 3-part Pass-2 grep extension + 14-gate checklist + LINE-REF-DRIFT P0.S5 ripple + CROSS-PATH-SYNC commitment + DEFERRED-CANARY-ENTRY-OMISSION + closure-audit-verdict-forwarding + `### Induction-surfaces-invariant-gaps` §11.4 deliberate-regression cycle. 7-instance threshold WARRANTED sub-rule elevation candidacy at next architect-side narrative work.
- **Pre-P1 Bundle 1 closure (2026-05-28)** — 7th. 7 disciplines applied preventively per closure narrative enumeration (LINE-REF-DRIFT + CROSS-PATH-SYNC + DEFERRED-CANARY-ENTRY-OMISSION + closure-audit verdict forwarding + CODE-TEMPLATE-MISIDENTIFICATION + Developer Pass-3 grep introduced as Bundle 1 carry-forward + Plan v2 absorption discipline). **STRONGLY WARRANTED elevation candidacy** banked at Bundle 1 closure.
- **Pre-P1 Bundle 2 Plan v2 (2026-05-28)** — 8th. 8 disciplines (Bundle 1's 7 + BIDIRECTIONAL Pass-3 file-count verification at Plan v2).
- **Pre-P1 Bundle 2 Plan v3 + closure (2026-05-28)** — 9th instance + ELEVATION EVENT LOCK. **9 disciplines preserved at Bundle 2 closure** per closure-audit ratification 2026-05-28: (1) LINE-REF-DRIFT preventive; (2) CROSS-PATH-SYNC-OMISSION preventive commitment; (3) DEFERRED-CANARY-ENTRY-OMISSION grep-verify; (4) closure-audit verdict forwarding 7th-cycle routinization; (5) CODE-TEMPLATE-MISIDENTIFICATION preventive (Apache + MIT text sha256-verified); (6) Developer Pass-3 grep at Phase 4 pre-implementation (Bundle 1 carry-forward); (7) §0 NEW catching-layer ACTIVATED in preventive mode at Phase 4 (0% drift validation); (8) BIDIRECTIONAL Pass-3 file-count verification at Plan v2; (9) BIDIRECTIONAL license-precision audit at Plan v3 (PI #3 absorption + EXCLUDED_PATHS architectural defense).
- **Pre-P1 Bundle 3 closure (2026-05-28)** — 10th instance (RETROACTIVE — banked at Bundle 4 closure-audit §4.2 (A) ratification 2026-05-28). **11 disciplines preserved at Bundle 3 closure** per Bundle 3 Plan v2 §5.4 enumeration (Bundle 2's 9 + Phase 0 explicit-per-bucket grep enumeration + cross-bundle architectural-coherence preventive [D2 AST invariant scope = Bundle 2 D6 SPDX scope]). The Bundle 3 closure narrative banked only the per-cycle preventive-COUNT trajectory (7→9→11) and never the doctrine's INSTANCE-COUNT increment — an auditor-side procedural gap (the auditor framed convergence as the trajectory metric at the Bundle 3 closure verdict) caught by the architect's fresh track-record read at Bundle 4 closure-audit. Retroactive 10th-instance banking is the honest correction.
- **Pre-P1 Bundle 4 closure (2026-05-28)** — 11th instance. **11 disciplines preserved at Bundle 4 closure** per Plan v1 §5.4 enumeration (sustained 11-floor; trajectory Bundle 1 [7] → Bundle 2 Plan v3 [9] → Bundle 3 Plan v2/closure [11] → Bundle 4 Plan v1/closure [11]). NEW 11th preventive vs Bundle 2's 9: Plan v1 §1.1 grep-verified BEFORE-code refresh (extends `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` behavioral-semantic axis to spec-text-vs-production-code representational integrity). Conservative one-per-closure granularity per closure-audit §4.2 minor note (Bundle 3 = 1, Bundle 4 = 1; no retroactive multi-artifact inflation).

**Discipline-stability evidence:**

3-instance trajectory across Bundle 1 (7 preventives) → Bundle 2 Plan v2 (8) → Bundle 2 Plan v3 (9) → Bundle 2 closure (9 preserved). 2 consecutive bundles with 7+ preventives each. Cross-actor validation: architect drafts preventive commitments at Plan v1; auditor confirms at Plan v1/v2/v3 verdicts; developer honors at Phase 4 implementation; closure-audit ratifies preservation. 0 silent rollbacks across 9 applications. Sub-rule elevated to numbered doctrine per locked elevation procedure (P0.R12-R15 closure 2026-05-25 sub-rule candidacy → Bundle 1 closure STRONGLY WARRANTED → Bundle 2 closure ELEVATION EVENT LOCKS at major architect-side narrative work).

**Operational rules:**

1. Plan v1 §5.4 (or equivalent section) MUST enumerate preventive disciplines applied at the cycle's artifacts. Enumeration is bookkeeping — not a count contest, but evidence of operational floor stabilization.
2. Cross-cycle trajectory is the load-bearing signal — single-cycle high counts without trajectory context don't bank. The signal is "discipline machinery matures over time", not "one cycle was unusually clean".
3. Distinguish between PREVENTIVE application (no real gap caught; discipline applied because it's locked) and CATCHING application (real gap surfaced + closed). Both are valuable but track separately. This doctrine counts preventives only.
4. When a cycle's preventive count exceeds the prior cycle by 1+, document the new preventive's lineage (which earlier cycle introduced it as a banked discipline; which doctrine extension applies). Trajectory continuity is the elevation criterion.
5. Catching-layer activation in preventive mode (i.e., layer fires but finds 0 drift) counts as a preventive instance per §0 NEW commitment Bundle 1 → Bundle 2 carry-forward precedent. Verification IS the prevention.

**Cross-disciplines:**

- **Parent (upstream)**: `### Spec-first review cycle for multi-day specs` — multi-day cycles structurally enable multi-discipline preventive convergence by providing multiple absorption surfaces (Phase 0 + Plan v1 + Plan v2 + Plan v3 + closure-audit).
- **Sibling**: `### Architect-reads-production-code-before-sign-off` — bidirectional verification disciplines feed into the preventive enumeration (BIDIRECTIONAL Pass-3 + BIDIRECTIONAL license-precision-audit are 2 of Bundle 2's 9 preventives).
- **Sibling**: `### Induction-surfaces-invariant-gaps` — in-cycle strengthening events are a different family (gap-catching) but share the locked-discipline pattern. Both contribute to operational floor maturation from different angles.
- **Child observation**: `Resilience-track-arc-completion` — arc-completion milestones tend to coincide with multi-discipline preventive convergence (P0.R12-R15 closure had both).

**Falsification clause (locked at elevation, mirrors prior 8 elevated doctrines):**

If a future cycle preserves a high preventive count (5+) at closure but a subsequent audit reveals one of the counted preventives was actually a CATCHING event (real gap surfaced + closed) misclassified as preventive, the count for that cycle adjusts downward + sub-rule track record adjusts accordingly. The load-bearing claim is "preventive application = locked discipline applied + no real gap surfaced". Falsification means a misclassification slipped through.

**Future instances** continue to be banked under this doctrine's track record. Trajectory continuity matters: if a future cycle ships with a sudden drop (e.g., Bundle 3 ships with 4 preventives after Bundle 2's 9), document the drop's cause (cycle simpler? disciplines retired?) — drops without rationale would signal regression in operational floor.

> Bundle 2 closure-audit ratification 2026-05-28 banking (extended at Bundle 4 closure-audit §4.2 (A) ratification 2026-05-28): this doctrine text is verbatim-sourced from auditor's Bundle 2 closure-audit verdict 2026-05-28 (proposed banking of `### Multi-discipline-preventive-convergence` doctrine elevation per locked sub-rule procedure). The track record was extended from 9 → 11 instances at Bundle 4 closure-audit (Bundle 3 retroactive 10th + Bundle 4 11th, per §4.2 (A) ratification — the Bundle 3 instance was an auditor-side omission at the Bundle 3 closure verdict, caught by the architect's fresh track-record read). Any future edit MUST preserve (a) the 11-instance trajectory enumeration in the track record (9 at elevation + Bundle 3 10th + Bundle 4 11th); (b) the 9-discipline enumeration at Bundle 2 closure; (c) the cross-actor validation framing; (d) the operational rules block (5 rules including catching-layer-in-preventive-mode counts as preventive). Future CLAUDE.md compactions MUST NOT drift these anchors.

### Developer-Pass-3-grep-at-Phase-4-pre-implementation

A dedicated catching-layer pass: the developer (Phase 4 implementer) re-greps the Plan v1/v2 enumeration against actual repo state at Phase 4 pre-implementation time, BEFORE any code mutation. This is structurally distinct from the architect's Pass-1 (Phase 0) and architect+auditor's Pass-2 (Plan v1/v2) — both upstream passes operate on the audit's mental model; Pass-3 operates against the actual disk-state at the time code will execute. When the upstream passes drift from disk-state (PowerShell measurement error, mechanical-script scope undercount, AST scope omission), Pass-3 catches the drift BEFORE Phase 4 commits a partial migration.

**Track record (3 instances at elevation 2026-05-28; sub-rule elevation event LOCKED at Bundle 3 closure per Q3 (a) RATIFIED):**

1. **Pre-P1 Bundle 1 Plan v2 (2026-05-28)** — 1st instance — **POWERSHELL-MEASUREMENT-ERROR sub-variant**. Architect's Phase 0 PowerShell `Get-Content | Measure-Object -Line` undercount mis-measured `everything_about_system.md` by 42% (claimed 6487 lines / 178 H2 sections on a 9214-line / 340 H2 file). Developer Pass-3 grep at Phase 4 pre-implementation surfaced the drift before code mutation; Plan v2 absorbed via expanded cluster table 12 → 19 chapters covering §1-§340.
2. **Pre-P1 Bundle 2 Plan v2 (2026-05-28)** — 2nd instance — **MECHANICAL-SCRIPT-SCOPE-UNDERCOUNT sub-variant**. Architect's Plan v1 SPDX scope estimated ~260 in-scope Python files; developer Pass-3 grep refined to 204 files (-21.5% drift) at Phase 4 pre-implementation. Plan v2 absorbed (corrected to 204; Plan v3 further narrowed to 202 with PI #3 `EXCLUDED_PATHS = ("core/_minifasnet/",)` for vendored MIT files). §0 NEW commitment EXTENSION (dual-axis file-count + semantic-correctness verification) banked at this catching event.
3. **Pre-P1 Bundle 3 Plan v2 (2026-05-28)** — 3rd instance — **AST-SCOPE-OMISSION sub-variant**. Architect's Plan v2 §1.8 enumeration of DEADLINE-MATH sites estimated ~28 sites; developer Pass-3 AST-based scan refined to 34 sites (+6 Compare-with-subtraction sites at pipeline.py:548 / 601 / 7230 / 7259 / 7390 / 7458 missed by the line-text grep). Plan v2 §1.14 LOCKED 44 assert→raise sites; developer Pass-3 surfaced 2 additional bootstrap classifier asserts at `bootstrap/classifier/hand_authored_scenarios.py:570+573` (caught by A4 detector during initial Phase 4 run). Sub-rule **ELEVATION EVENT LOCKED** at this closure per Q3 (a) RATIFIED + 3-instance threshold reached.

**4-step protocol (LOCKED at Bundle 3 closure per Q3 (a) RATIFIED):**

1. **Phase 0 baseline**: architect performs Pass-1 grep to establish enumeration baseline (file counts, surface counts, AST shape counts). Reported in Phase 0 §1 grep findings.
2. **Plan v1/v2 enumeration**: architect (Pass-2 at draft time) + auditor (Pass-2 at review time) refine the enumeration; absorption into Plan v1 §1.x table or Plan v2 §1.x absorption table. Either both passes converge on a clean enumeration (OPTIONAL-Plan-v2 path) or one surfaces a precision item.
3. **Developer Pass-3 grep at Phase 4 pre-implementation**: developer re-greps the locked enumeration against actual disk-state BEFORE code mutation. Drift outcomes route to (a) §0 NEW commitment STOP (architect + auditor re-engaged to absorb the drift via Plan v2/v3 expansion) OR (b) §0 NEW commitment PROCEED (drift within ±10% tolerance + semantically subsumed by the locked surface so developer proceeds with extended scope documented in closure narrative).
4. **Closure narrative banking**: developer documents Pass-3 outcome (clean = preventive instance; drift = catching instance + sub-variant classification). Architect closure-audit ratifies the banking.

**Discipline-stability evidence:**

- 3 consecutive bundles' upstream-pass drift caught at Phase 4 pre-implementation without silent rollback or deferred-fix routing.
- Cross-actor independence — architect performs Pass-1 + Pass-2 at architect-side artifacts; developer performs Pass-3 at Phase 4 pre-implementation surface; auditor cross-verifies at Plan v2/v3 review + closure-audit. Catching events surface at the developer-side surface, not folded back into architect's grep work.
- Sub-variant taxonomy grew organically across 3 instances: POWERSHELL-MEASUREMENT-ERROR (Bundle 1) → MECHANICAL-SCRIPT-SCOPE-UNDERCOUNT (Bundle 2) → AST-SCOPE-OMISSION (Bundle 3). Each instance contributed a distinct upstream-drift mechanism the Pass-3 layer catches.

**Operational rules:**

1. Developer's Phase 4 pre-implementation MUST include a Pass-3 grep that re-greps the locked Plan v1/v2 enumeration against actual disk-state BEFORE any code mutation begins. Pass-3 IS the precondition for code-mutation, not a parallel discipline.
2. Pass-3 outcomes are first-class artifacts — log them in the developer handoff with explicit "Plan v1/v2 locked count = N; Pass-3 disk-state count = M; delta = ±X%; sub-variant classification". Clean (0% drift) = preventive instance; drift = catching instance routed per §0 NEW commitment EXTENSION (file-count axis + semantic-correctness axis).
3. When Pass-3 surfaces a count drift > ±10% OR a semantic-correctness gap (e.g., the locked surface set excludes files that the production-code shape requires), §0 NEW commitment STOPS code mutation + re-engages architect + auditor for Plan v2/v3 absorption. Do NOT proceed-with-extended-scope when the drift exceeds the tolerance band.
4. Pass-3 covers BOTH file-count axis (numeric drift) AND semantic-correctness axis (e.g., does the locked surface set match production-code shape; does the AST detector's scope match the production-code scope). §0 NEW commitment EXTENSION dual-axis verification locks at Bundle 2 closure precedent.

**Cross-disciplines (parent-child relationships):**

- **Parent (upstream)**: `### Pass-2-grep-auditor-verified-before-Plan-v1-approval` — Pass-2 establishes the locked enumeration that Pass-3 re-verifies at Phase 4. Pass-3 is the developer-side catching layer that backstops the upstream architect+auditor Pass-2 convergence.
- **Parent (upstream)**: `### Pre-audit-quantifier-precision-refined-by-grep` — pre-audit quantifier approximations refined by Phase 0 grep is the UPSTREAM refinement event; Pass-3 is the DOWNSTREAM refinement event when upstream refinements still drift from disk-state. Both share the "grep-refines-imprecise-framings" load-bearing claim.
- **Sibling**: `### Architect-reads-production-code-before-sign-off` — both disciplines are about claim-vs-reality drift caught at named surface. Pass-3 catches drift at Phase 4 pre-implementation; Architect-reads-production-code catches drift at closure-audit. Same grep-verify discipline applied at different cycle phases.
- **Sibling**: `### Multi-discipline-preventive-convergence` — Pass-3 in preventive mode (0% drift) counts as one of the preventive disciplines per the parent's Rule 5 ("catching-layer activation in preventive mode counts as a preventive instance").

**Falsification clause (locked at elevation, mirrors prior 9 elevated doctrines):**

If a future cycle's Pass-3 grep at Phase 4 pre-implementation PASSED CLEANLY (no drift surfaced) but a subsequent closure-audit OR auditor verification surfaced a real Plan v1/v2 enumeration drift that the Pass-3 layer should have caught with a proper re-grep, the doctrine demotes back to architect-memory + falsification banking applies. The load-bearing claim is "developer Pass-3 catches what upstream Pass-1/Pass-2 misses BEFORE code-mutation"; falsification means Pass-3 itself missed a real drift that surfaced later.

**Future instances** continue to be banked under this doctrine's track record. Sub-variant taxonomy may grow as new upstream-drift mechanisms surface. Doctrine matures rather than re-elevating at higher thresholds.

> Bundle 3 closure-audit ratification 2026-05-28 banking: this doctrine text is verbatim-sourced from auditor's Bundle 3 closure-audit Q3 (a) RATIFIED verdict 2026-05-28 (proposed banking of `### Developer-Pass-3-grep-at-Phase-4-pre-implementation` doctrine elevation per locked sub-rule procedure + 3-instance threshold reached). Any future edit MUST preserve (a) the 4-step protocol block; (b) the 3-instance sub-variant taxonomy (POWERSHELL-MEASUREMENT-ERROR + MECHANICAL-SCRIPT-SCOPE-UNDERCOUNT + AST-SCOPE-OMISSION); (c) the dual-axis (file-count + semantic-correctness) §0 NEW commitment EXTENSION framing; (d) the operational rules block (4 rules); (e) the parent-sibling cross-disciplines structure; (f) the falsification clause. Future CLAUDE.md compactions MUST NOT drift these anchors.

### Spec-first review cycle for multi-day specs

For sub-PRs estimated > 1 day, the workflow is: **Phase 0 audit → D1-Dn decisions surfaced → Plan v1 → architect/auditor review → Plan v2 → code**. Phase 0 audit is pure documentation (grep-verified findings, zero production-code changes); Plan v1 is the first complete spec; architect/auditor feedback drives a Plan v2 revision before any code lands.

**Track record (batting 15-for-15):** P0.6 (Store-pattern migration), P0.7 (typed session state), P0.8 (timeout protection extraction), P0.9 (schema migrations versioning), P0.10 (legacy router deletion), P0.0.7 (event log foundation), P0.S1 (anti-spoof on every face match — Phase 0 audit caught the wrong-premise gap at progressive_enroll site 5 BEFORE any code was written; same pattern as P0.10's Phase 0), P0.S6 (secrets management — Phase 0 audit caught the wrong-premise gap re: log-leak surface; actual gaps were orphan credentials + structural-invariant absence + history-scan absence, not the assumed log-leak surface), P0.S7 (Phase 3B D-A SHARED CONTEXT — Phase 0 audit decomposed S107's 5-deferral `conversation_log` retrieval into 4 explicit follow-ups D-A through D-E; identified D-A as the first slice and surfaced 3 missed threats T-A/T-B/T-C before any code phase began), P0.S7.2 (Cross-Session Memory Retrieval Gap — Phase 0 audit decomposed the 2026-05-18 Session A → Session B canary's failure mode into the load-bearing γ + κ two-part fix; identified κ multi-person assistant-turn extraction as the missing producer side AND γ MEMORY HONESTY DISCIPLINE as the consumer-side prompt anchor before any code phase began; surfaced 3 missed threats T-A/T-B/T-C around disputed sessions + producer-side audience_ids + privacy semantics), P0.S7.D-C (Delete `_build_cross_person_excerpts` legacy block — Phase 0 audit grep-mapped the function's 10-surface dependency fan-out; pre-Phase-0 assumed premise was "clean 3-site deletion ~quarter-day" but grep surfaced 6 D-decisions including D3 disputed-identity gap-verification + D2 summary-field repoint semantic + the two-stage flag-gate strategy that preserves canary-gate semantics; banked as the first instance of "scope-expansion-via-Phase-0" informal observation distinct from sub-pattern A wrong-premise), P0.S7.D-B (Kuzu v3 schema bump — Phase 0 audit reversed the S107 + S112 deferral by grep-verifying that P0.S7.2 κ extraction had falsified the deferral premise; 8 surfaces vs predicted 8 — NOT scope-expansion; banked as the first instance of "deferral-rationale-expires-when-downstream-ships" informal observation distinct from both sub-pattern A and scope-expansion), P0.S7.D-D (RoomOrchestrator class extraction — Phase 0 audit reset the premise from "refactor 50+ `_active_sessions[pid]` access sites — 5-7 days" to "consolidate 7 module-level room helpers — ~1 to 1.5 days." P0.7 + P0.6.6 had already done the `_active_sessions[pid]` migration under different class names; the actual D-D scope was the 7 module-level helpers. Sub-pattern A 5th instance — THE THRESHOLD-CROSSING EVENT for `### Phase-0-catches-wrong-premise` doctrine elevation), P0.S7.D-E (γ targeted fix for multi-speaker per-speaker history — Phase 0 audit reset the premise from "Part 2 Components 1-3 multi-speaker conversation_turn redesign — 3-5 days" to "single helper that closes ~80% of the gap — ~5.5h." Partial falsification — γ doesn't cover the full α refactor's contract; the held subset stays scheduled if canary surfaces evidence γ is insufficient. Banked as `feedback_partial_falsification_tentative.md` 1st instance at architect-memory ONLY, NOT CLAUDE.md doctrine — distinct from full wrong-premise sub-pattern A), P0.S7.5 (bundled-queue canary follow-up — Phase 0 audit decomposed 2026-05-19 canary's 5 distinct failure modes into 5 D-decisions D1-D5 with named edit sites per file/line. Auditor-Q5 estimate FIRST ON-TARGET across 4 instances [12-19 forecast → 16 actual]; Phase 0 granularity sub-observation banked: estimate accuracy correlates with audit D-decision granularity. Canary-finding 3rd instance; partial-falsification 2nd instance at architect-memory). Spec-time investment pays back 2-4× in mid-flight rework avoided — every cycle that skipped Phase 0 hit larger surprises.

**Sub-pattern A graduated to numbered doctrine on P0.S7.D-D closure (2026-05-19).** The 5-instance track record (P0.10, P0.S1, P0.S6, P0.S7, P0.S7.D-D) crossed the 5+ threshold; the doctrine elevation lives at the new `### Phase-0-catches-wrong-premise` heading below. The interim instances that did NOT bump the count (P0.S7.2, P0.S7.D-C, P0.S7.D-B) are catalogued under their respective informal observations (canary-finding tracker, scope-expansion-via-Phase-0, deferral-rationale-expires-when-downstream-ships) — those remain distinct from wrong-premise. Future wrong-premise instances continue to accumulate under the new doctrine's track record.

**Informal observations toward future doctrines (currently below the 5+ threshold for `###` elevation):**

- **Canary-gate override** — 1 instance (P0.S7.D-C). A spec explicitly reverses its own canary-gate per user strategic direction, then quality-mitigates via a two-stage flag-gate that preserves the canary semantic via rollback path while unblocking the user's bundled queue. If pattern recurs 5+ times, may elevate to `### Canary-gate-overrides-need-quality-mitigation` doctrine.
- **Scope-expansion-via-Phase-0** — 1 instance (P0.S7.D-C). Phase 0 audit finds the deletion/cleanup scope is N× larger than pre-audit assumption (10 surfaces vs assumed 3; 6 D-decisions vs assumed 1; D3 disputed-identity gap-verification needed before deletion is safe). Distinct from sub-pattern A wrong-premise: this isn't "THE problem is somewhere else" but "the cleanup is more complex than expected." D-B Phase 0 audit §5.1 explicitly checked this hypothesis and found D-B is NOT a scope-expansion instance (8 surfaces vs predicted 8 — pre-audit estimate held within ~25%). Useful refinement: the observation may be specific to deletion/cleanup work rather than additive work. If recurs 5+ times, may elevate to `### Phase-0-catches-scope-expansion` doctrine.
- **Deferral-rationale-expires-when-downstream-ships** — 1 instance (P0.S7.D-B). A previously-deferred decision becomes load-bearing because downstream work changed the threat landscape. The deferral was correct AT THE TIME but the premise that justified it (e.g. "no concrete active leak exists now") no longer holds after the downstream ship. Distinct from sub-pattern A (architect's mental model wasn't wrong — the threat surface itself moved) AND distinct from scope-expansion-via-Phase-0 (the scope is bounded by the new feature, not larger than expected). P0.S7.D-B specifics: S107 + S112 deferred Kuzu v3 ("SQL filter sufficient; no concrete active leak"); P0.S7.2 κ multi-person assistant-turn extraction shipped 2026-05-19 and falsified the premise by writing personal-tier `received_*`/`witnessed_*` facts to brain.db whose graph rebuild ingests them as RELATES_TO edges with no privacy filter. The deferred decision needed re-evaluation when the downstream feature shipped. If pattern recurs 5+ times, may elevate to `### Deferred-decisions-need-re-evaluation-on-downstream-ship` doctrine.

**Operational rules:**
1. Phase 0 is grep-verified findings reported BEFORE any test code is written. Skip this and the rework cost exceeds the Phase 0 cost (validated empirically across P0.2-P0.5).
2. Plan v1 surfaces decisions (D1-Dn) explicitly; architect/auditor sign-off locks them before Plan v2.
3. Plan v2 may revise Plan v1 in light of feedback; subsequent code follows v2's locked structure. No "while I'm here" deviations.

### Spec-contracts-not-implementations

Architect specs describe **what invariants must hold** (the contract), not how to satisfy them (the implementation). Developers find the best implementation within the contract. When a spec prescribes implementation details, it forecloses the developer's mechanism-discovery loop and reliably produces worse code than necessary.

**Why this matters:** the developer has full visibility into the actual code, runtime state, surrounding patterns, and adjacent constraints the spec author cannot pre-load. Specs that lock contracts let the developer's local knowledge improve the mechanism; specs that lock mechanisms turn the developer into a transcription typist.

**Examples of contract vs implementation:**
- Contract: "every paired-write site must use a `_mark_X_dirty()` sentinel before the cross-storage write." Implementation: which file, which exact name, which line — developer's call.
- Contract: "the band-divergence trigger fires when `utt_band ∈ {gap, short_hard}` and the rule that fired isn't the band's expected rule." Implementation: where the mapping lives, what data type — developer's call (this is P0.10.1 F2: `EXPECTED_RULES_BY_BAND` belongs in `core/reconciler.py`, not pipeline.py inline).

### Developer-improves-on-spec-by-reading-carefully

When implementation reveals a better path that preserves the spec's architectural intent, bank the improvement explicitly in the closure report so the architect/auditor sees the deviation + rationale.

**Track record (batting 6-for-6):**
- **P0.8.2 F2** — spec named external call sites; developer's caller audit found the actual contract was internal (`ask_retry_text` doesn't accept `include_tools` as a parameter by design), so F2 verified the internal contract instead.
- **P0.9.1** — spec sketched a fresh `init_ledger()`; developer made it self-evolving (idempotent ALTER adding `is_initial` to pre-P0.9 ledgers) so the classifier_scenarios.db schema upgrade rode the same code path.
- **P0.9.2** — spec defined 4-tuple migrations; developer split `verify_post`/`verify_present` because conflating them would let bootstrap stamp `is_initial=1` on a partially-backfilled DB (S107 P3A.6 / S95 P3A.4 cases).
- **P0.10 Block C** — spec said "extend the existing divergence-log block with more fields, don't change trigger"; Step 7's legacy deletion makes the original trigger (`_rc_decision.action != _routing_action`) unworkable; developer retargeted to band-divergence detection, preserving Block E's gate criteria semantically.
- **P0.0.7 Step 5 polish** — reviewer's P0.4 remediation said "annotate the 12 hook-site try/except blocks with `# OPTIONAL:`"; developer instead consolidated to a single `safe_emit_sync(...)` helper in `core/event_log/producer.py` with one P0.4-annotated except — 12 violations → 1 annotated except + 12 unannotated call sites; future hooks automatically inherit the swallow-discipline. Same shape as P0.8's `_TOOL_HANDLERS` consolidation. Strictly better than the annotation patch the reviewer proposed.
- **P0.S1 Phase 2 §14b.2 route choice** — Plan v2 offered AST graph walk (§3.2 primary) OR marker-comment fallback (§14b.2) for same-frame discipline. Production code uses `run_in_executor(None, embedder.embed, _crop)` which makes `embedder.embed` a Name expression passed to `run_in_executor`, not a Call node directly. The AST graph walk's variable-provenance algorithm would have to model the `run_in_executor` indirection — implementable but brittle, and brittleness in a structural invariant is exactly what makes invariants drift. Developer chose marker-comment route: `# P0S1-C0:` annotation at call site + K-line lookahead asserting `_crop = frame[...]`, `embedder.embed(_crop)`, and `verify_live(frame, ...) OR _classify_anti_spoof_verdict(frame, ...)` all reference the same `frame` variable. Strictly equivalent contract proof, cleaner under the actual code shape. Bundled with the VisionFramePayload schema widening from `bool` to `Optional[bool]` (Phase 2 needed 3-state for ANTI_SPOOF_REASON_UNAVAILABLE; P0.0.7 prerequisite locked 2-state; widening preserves architectural intent while accommodating the new semantic).

Pairs with **spec-first review cycle** (the discipline that produces these moments) and **spec-contracts-not-implementations** (the architect-side framing that makes them welcome). When developer-spec-improvement happens, flag explicitly in the closure report — silent improvements drift the contract and erode the architect/auditor's read on what shipped.

---

## Project Overview

KaraOS is the Layer D cognitive runtime middleware for embodied AI — the layer above motor control and below natural-language orchestration. The runtime targets a 3-5 year market-defining horizon as the standard middleware for any embodied AI agent.

Two stacks ship in tandem: (1) the companion stack — today's behavior, AI robot dog reference application; (2) the robotics stack — embodied runtime landing in P1 with TurtleBot4 (Gazebo simulator) as reference.

**Companion stack** (today): Sees faces → identifies people → greets by name → holds voice conversations → remembers people across sessions.

**Robotics stack** (P1): Commitment store + scheduler + policy engine + verifier registry + adapter SDK + MCP server. Robot-agnostic via the adapter SDK.

**Dev machine:** Windows 11 laptop (DirectShow camera)
**Production target:** Jetson AGX Orin 32GB (V4L2, faiss-gpu, TensorRT)
**Project root:** `C:\Users\jagan\dog-ai\dog-ai\`
**Run:** `python pipeline.py`
**Venv:** `venv\Scripts\activate` (Windows) / `source venv/bin/activate` (Linux)
**Tests:** `pytest` (4259 collected, asyncio_mode=auto)

---

## Architecture

```
pipeline.py          — Main async event loop
core/
  config.py          — ALL constants (single source of truth — change settings here only)
  vision.py          — RetinaFace (InsightFace buffalo_l) + AdaFace IR101 + SORT tracking
  db.py              — SQLite WAL + FAISS face database
  brain.py           — LLM interface (Together.ai + Ollama fallback)
  brain_agent.py     — Multi-agent knowledge pipeline (extraction, graph, embeddings, prefs)
  audio.py           — Whisper STT + Kokoro TTS (English only)
  emotion.py         — j-hartmann distilroberta-base emotion classifier
  state.py           — Atomic JSON state file (pipeline → dashboard IPC)
  sort.py            — SORT face tracking (Kalman filter, Hungarian assignment)
  voice.py           — SpeechBrain ECAPA-TDNN speaker identification
enroll.py            — Standalone CLI enrollment (has anti-spoofing)
delete_person.py     — CLI tool to remove a person
dog-ai-dashboard/    — Next.js dashboard
faces/               — Runtime data: faces.db, faiss.index, brain.db, brain_graph/, state.json
models/              — ONNX models
```

---

## Key Config Values (verified from config.py — do NOT guess these)

| Constant | Value | Notes |
|---|---|---|
| `RECOGNITION_THRESHOLD` | 0.28 | cosine similarity for face match (raised from 0.18 — AdaFace IR101 stable EER region) |
| `MAX_EMBEDDINGS` | 50 | max face embeddings per person |
| `FACE_DIVERSITY_THRESHOLD` | 0.92 | skip too-similar embedding |
| `SELF_UPDATE_THRESHOLD` | 0.45 | min conf to update gallery (must be > RECOGNITION_THRESHOLD; raised from 0.32 after uncle-false-match incident) |
| `SELF_UPDATE_CENTROID_MIN` | 0.55 | reject recognition_update writes whose cosine to gallery centroid is below this |
| `STRANGER_VOICE_TTL_DAYS` | 3 | prune stranger voice profiles that never reached N_INITIAL_VOICE samples |
| `DISPUTE_MAX_DURATION` | 180s | force-close identity-disputed sessions after this long without resolution |
| `DISPUTE_RENAME_BLOCK_THRESHOLD` | 3 | blocked disputed-rename attempts in one session before watchdog fires |
| `SCHEMA_NORM_THRESHOLD` | 0.97 | cosine above this = auto-merge attribute synonyms (raised from 0.95) |
| `GREET_COOLDOWN` | 300s | re-greet cooldown |
| `FACE_LOSS_GRACE` | 10s | keep session alive after face leaves |
| `VOICE_SESSION_TIMEOUT` | 30s | voice-only session timeout |
| `CHAT_MODEL` | `meta-llama/Llama-3.3-70B-Instruct-Turbo` | Together.ai |
| `EXTRACT_MODEL` | `meta-llama/Llama-3.3-70B-Instruct-Turbo` | same as chat |
| `EMBED_MODEL` | `intfloat/multilingual-e5-large-instruct` | 1024-dim |
| `OLLAMA_MODEL` | `qwen2.5:7b` | offline fallback |
| `SILENCE_DURATION` | 1.5s | hard end-of-turn fallback |
| `SMART_TURN_SILENCE` | 0.5s | neural turn-end trigger |
| `SMART_TURN_THRESHOLD` | 0.80 | confidence cutoff |
| `FILLER_ENABLED` | False | disabled (feels robotic) |
| `VAD_SWITCH` | False | RMS threshold (not Silero) on dev laptop |
| `ANTISPOOFING_ENABLED` | True | MiniFASNet liveness |
| `EMOTION_ENABLED` | True | rolling 3-turn emotion window |
| `SORT_DETECT_EVERY` | 5 | RetinaFace every 5th frame |
| `GRAPH_SCHEMA_VERSION` | 2 | Kuzu schema version |
| `KNOWLEDGE_MAX_ROWS` | 2000 | brain.db pruning cap |
| `DREAM_IDLE_MINUTES` | 5 | idle before dream() runs |
| `DREAM_COOLDOWN` | 3600s | min gap between dream runs |
| `KAIROS_SILENCE_THRESHOLD` | 30s | proactive question trigger |

---

## Module Roles (brief)

**core/vision.py** — Three classes + four quality functions:
- `FaceDetector` — buffalo_l RetinaFace + SORT tracking. Detect every 5th frame, Kalman predicts in between.
- `FaceEmbedder` — AdaFace IR101 ONNX, 512-dim, GPU.
- `Camera` — DirectShow (Windows) / V4L2 (Linux). Reconnect logic.
- `AntiSpoofChecker` — MiniFASNet, fail-safe (returns True if unavailable).
- `LipTracker` — inter-frame pixel diff, extends recording when lips moving.
- `face_quality_score()` — V1: size/blur/brightness gate.
- `estimate_yaw_from_landmarks()` — V2: skip side-on faces (|yaw|>60°).
- `TemporalEmbeddingBuffer` — V3: mean-pool 5-frame embeddings. Keyed by SORT track_id.
- `adaptive_threshold()` — V4: quality-scaled recognition threshold.

**core/db.py** — FaceDB class:
- SQLite WAL mode. FAISS IndexFlatIP (exact cosine search).
- Tables: `persons`, `embeddings` (with BLOB), `conversation_log`, `voice_embeddings`, `system_identity`, `silent_observations`, `visitor_log`.
- `add_embedding()` — diversity-gated, enforces MAX_EMBEDDINGS cap. Returns bool.
- `delete_person()` — always calls `_rebuild_faiss()` after deletion.
- `recognize()` — returns (person_id, name, score). score returned even when unrecognized.
- `load_conversation_history()` — full history, no DB-level cap (bug I4).

**core/brain.py** — LLM routing:
- Primary: Together.ai `meta-llama/Llama-3.3-70B-Instruct-Turbo`. Streaming + function calling.
- Fallback: Ollama qwen2.5:7b. Stateless Q&A only (no tools, no memory writes).
- 6 tools: `update_person_name`, `update_system_name`, `search_web`, `shutdown`, `search_memory`, `report_identity_mismatch`. Privileges governed by `TOOL_PRIVILEGES` table in `core/config.py` (fail-closed).
- `ask()` → `(response_text, list[tool_calls])`.
- `ask_offline()` — last 10 turns, no tools.
- `ping_together()` — 5s health check.
- Web search: Tavily API (3 results, 8s timeout) via `search_web` tool.
- Context compression: MicroCompact (truncate old messages) → AutoCompact (LLM summarize) → hard trim.

**core/brain_agent.py** — Multi-agent knowledge pipeline:
- `BrainDB` — brain.db (WAL). Tables: `knowledge`, `schema_catalog`, `agent_log`, `prompt_prefs`, `object_sightings`, `object_pattern_questions`, `episodes`, `presence_log`, `proactive_nudges`, `watchdog_alerts`, `social_mentions`, `predicate_stats`, `household_facts`, `inter_person_relationships`, `shadow_persons`.
- `TriageAgent` — fast no-LLM filter.
- `ExtractionAgent` — LLM JSON extraction of entities+facts.
- `ContradictionAgent` — LLM checks new facts vs stored. Returns REPLACE or COMPATIBLE.
- `PromptPrefAgent` — per-session communication preference learning (5 pref types). Auto-confirms at 3 sessions.
- `EmbeddingAgent` — Together.ai multilingual-e5-large-instruct. In-memory cache.
- `GraphDB` — Kuzu embedded property graph. 1-hop traversal for entity relationships. Schema v2.
- `SpatialMemoryAgent` — YOLO11 object sightings (disabled: VISION_YOLO_ENABLED=False).
- `PatternAnalysisAgent` — generates proactive questions from sighting patterns.
- `FrictionDetectionAgent` — detects when user behavior contradicts active prefs. Escalates injection urgency.
- `HouseholdExtractionAgent` — household facts, inter-person relationships, shadow persons.
- `BrainOrchestrator` — coordinates all agents. event-triggered via `notify()`. `dream()` runs pruning/decay.

**core/audio.py** — English only:
- STT: faster-whisper large-v3-turbo, GPU float16, language="en" always.
- TTS: Kokoro ONNX (af_heart, primary) → Piper English (en_US-lessac-medium.onnx, fallback). edge-tts removed.
- VAD: RMS threshold (default, laptop) or Silero (Jetson).
- Smart-Turn: ~8MB ONNX model. Neural end-of-turn at 0.5s silence.
- Lip tracking: extends recording when lips still moving (max 2s extension).
- Barge-in: REMOVED. Waiting for ReSpeaker hardware. Do NOT re-add `_vad_interrupt_listener`.

**pipeline.py** — Main loop:
- Multi-session: `_active_sessions: dict[str, dict]` — each person has independent session.
- `_open_session()` / `_close_session()` / `_primary_person_id()` helpers.
- `CloudState`: ONLINE → SICK → OFFLINE → recovery. Background retry every 30s.
- `_execute_tool()`: dispatches all 6 tools.
- `_kairos_tick()`: proactive question if user silent >30s. Logs turns to DB and notifies brain orchestrator.
- `_dream_loop()`: triggers `brain_orchestrator.dream()` during 5min+ idle windows.
- Anti-spoofing: gates greeting of known person only (NOT enrollment — see B2).
- SIGINT → graceful shutdown. Double SIGINT → `os._exit(1)`.

---

## Historical record (bug audit + session table) — see `docs/history/`

Moved 2026-07-30. `docs/history/BUG-AUDIT-2026-04-10.md` +
`docs/history/COMPLETED-SESSIONS.md`. Nothing deleted.

## Pending Work

### Active bugs to fix (discuss before starting)
- (All previously listed P1–P4 bugs and A/B/I/G items resolved through Session 40)
- **P0.S7.D-C Stage 2 — hard-delete `_build_cross_person_excerpts`** (banked follow-up dependency, NOT yet scheduled). Trigger condition: user runs a multi-person canary AFTER all bundled-queue items have shipped (D-A + D-C + D-B + D-D + D-E + γ strengthening as P0.S7.4). On canary PASS — brain demonstrates cross-session recall + multi-person room context correctly + autonomous `search_memory` call per γ strengthening + no regressions in disputed-session / addressed_to / session-boundary surfaces — file Stage 2 follow-up PR. Stage 2 scope: delete `_build_cross_person_excerpts` function (pipeline.py:1202-1302, ~89 LOC) + `CROSS_PERSON_EXCERPTS_ENABLED` config flag + flag-gate at pipeline.py:5419 + dead prompt_addendum prepending path at pipeline.py:5448-5449 + flag-related tests (D-C Phase 1 tests 1+2 + Phase 3 D7 AST invariant test). If canary FAILS → flip `CROSS_PERSON_EXCERPTS_ENABLED=True` for one-flag-flip rollback; Stage 2 stays unfiled until canary passes. Stage 2 closure narrative references back to P0.S7.D-C as the Stage 1 of the two-stage approach.
- **P0.S7.4 real-LLM validation** (banked follow-up, NOT yet scheduled). Validates the strengthened γ MEMORY HONESTY DISCIPLINE bullet via the same bundled-queue canary per P0.S7.2 §11.10 re-canary discipline. Target: brain calls `search_memory` IMMEDIATELY on first mention of an unrecognized reference (0 forbidden-first-response hedges in canary log). If canary still shows pre-retrieval hedging, file P0.S7.5 to further strengthen the prompt OR investigate LLM tool-calling compliance ceiling.
- **P0.S7.D-B defensive-skip cleanup** (banked follow-up, NOT yet scheduled). The `if not _filtering:` skip in `BrainOrchestrator.get_context` (graph path, around `core/brain_agent.py:8038`) was the pre-D-B defensive guard preventing cross-person graph leaks. Under v3, the Cypher-level filter in `get_graph_context` enforces the same property structurally — so the Python-side skip becomes redundant-but-harmless. Future cleanup PR removes the skip once D-B's privacy semantic is canary-validated (bundled-queue canary post-D-E). On canary PASS — graph filter behaves correctly + no regressions in `get_context` callers — file cleanup PR. Until then, the skip stays in place as belt-and-braces per Plan v2 §3.4 framing.
- **P0.S7.D-D Stage 2 — hard-delete RoomOrchestrator shim layer + migrate 130 test sites** (banked follow-up dependency, NOT yet scheduled). Trigger condition: same bundled-queue canary as D-C Stage 2 — user runs a multi-person canary AFTER all bundled-queue items have shipped (D-A + D-C + D-B + D-D + D-E + γ strengthening). On canary PASS — RoomOrchestrator + 7 class methods behave correctly end-to-end + no regressions in the 130 test sites via the shim layer — file Stage 2 follow-up PR. Combined-PR candidate with D-C Stage 2 (same trigger; same scope shape). Stage 2 scope: (a) delete 7 module-level shim functions from pipeline.py (`_compute_room_audience`, `_kairos_preferred_speaker`, `_build_cross_person_excerpts`, `_build_shared_context_block`, `_build_room_block`, `_fetch_recent_room_context`, `_on_room_end`); (b) migrate 130 test sites across 7 test files from `_build_room_block(...)` → `_room_orchestrator.build_room_block(...)` shape (or introduce a `room_orchestrator` test fixture); (c) delete the autouse-fixture init block (Stage 1 shim contract no longer needed); (d) delete the `_init_room_orchestrator` function (Stage 2 lifts the class instantiation inline into `run()`). If canary FAILS → keep the shim layer in place; no rollback needed (shims preserve legacy semantics).
- **P0.S7 bundled-queue RE-CANARY** (READY TO RUN IMMEDIATELY — POST-P0.S7.5 MILESTONE REACHED 2026-05-19). After P0.S7.5 shipped the 5 root-cause fixes (D1 nudge persistence + D2 SHARED CONTEXT widening + D3 canonical-ack await + D4 KNOWN SPEAKER IDENTITY block + D5 FABRICATED ABSENCE anti-pattern), the RE-CANARY runs IMMEDIATELY per auditor Q6 (no observation window). Same Lexi-visitor scenario from the 2026-05-19 failure run. **Expected behavior chain**: (1) Turn 1 of Jagan's return → VISITOR_ALERT injects (persistent; D1); (2) `[visitor_id:lexi_xxx]` marker in `prompt_addendum` every turn until expires/dismissed; (3) VISITOR CONTEXT block renders with explicit `search_memory(person_name='Lexi')` directive (P0.S7.2/4 work already in place); (4) Brain calls `search_memory('Lexi', ...)` → returns Lexi's facts; (5) Brain answers correctly with Lexi-specific content (no "No one was here" confabulation — D5 anti-pattern bullet active); (6) SHARED CONTEXT block (D2 widened) ALSO surfaces persisted room turns where Jagan was in `audience_ids`; (7) Canonical ack speaks the correct name on rename (D3 await); (8) No `update_person_name` repeat after Lexi rename complete (D4 KNOWN SPEAKER IDENTITY block). **On RE-CANARY PASS** → fires combined Stage 2 PR (D-C Stage 2 + D-D Stage 2 hard-deletes + 130 test-site migrations). **On RE-CANARY FAIL with new root cause** → diagnose; file follow-up spec. Until RE-CANARY runs, all the fixes hold via CI test coverage (~17 tests across Phase 1+2+3 covering nudge persistence, D2 fallback semantic, D3 await contract, D4 block gating, D5 anti-pattern content).
- **P0.S7 bundled-queue canary** (ORIGINAL POST-D-E MILESTONE — SUPERSEDED by P0.S7.5 RE-CANARY above 2026-05-19). All architectural items shipped: D-A (SHARED CONTEXT block) + D-C Stage 1 (legacy block flag-gate) + D-B (Kuzu v3 schema bump) + D-D Stage 1 (RoomOrchestrator class extraction) + γ (P0.S7.4 MEMORY HONESTY DISCIPLINE strengthening) + D-E (per-speaker history γ targeted fix). Multi-person canary validates the bundled set end-to-end. **On canary PASS** → triggers Stage 2 cleanups (D-C Stage 2 + D-D Stage 2 combined PR candidate). **On canary FAIL with D-E γ-related root cause** → file full α refactor (Part 2 Components 1-3 multi-speaker conversation_turn redesign) as separate post-canary spec. γ stays in place (additive; no rollback). **On canary FAIL with D-B/D-C/D-D/γ root cause** → file targeted follow-ups; rollback paths exist where needed (flag-flip for D-C Stage 1; one-flag-flip for `CROSS_PERSON_EXCERPTS_ENABLED`).
- **P0.S7.D-E full α refactor (Part 2 Components 1-3 multi-speaker conversation_turn redesign)** — NOT scheduled unless the bundled-queue canary surfaces evidence γ alone is insufficient. γ closes ~80% of the gap (per-speaker history append for secondary speakers); full α covers the remaining ~20% (multi-speaker conversation_turn refactor that removes the `_cur_pid` singular primary model + interleaved history with speaker tags). Architect's strict-read line: γ is partial-falsification only; the held subset stays scheduled. If canary PASS with γ alone → α stays deferred indefinitely. If canary FAIL with multi-speaker root cause → file α as separate post-canary spec.
- **P0.10 validation window OPEN** — Phase 2 deletion shipped 2026-05-17. Daily checklist + gate criteria live in `tests/p0_10_validation_runbook.md`. Closure unlocks the follow-up PR (DELETES the shadow block + `ROUTING_USE_RECONCILER` flag + B2 fail-safe + their tests; KEEPS the new reconciler rule + LOWER_BOUND attrs + Bug-W regression + RULES-ordering invariant + N2-N6 contracts + AST single-write-site test).
- **P0.0 CI scaffold live** (P0.0 + P0.0.1 + P0.0.2 closures 2026-05-08; Pre-P1 Bundle 1 D1 consolidation 2026-05-28 supersedes the previously-listed stale CI-scaffold-missing bullets): 4 GitHub Actions workflows under `.github/workflows/` (`fast.yml` per push/PR + `slow.yml` nightly + manual + `security.yml` weekly + push-on-requirements-change + `trufflehog.yml` PR diff + Sunday full-history) + 4 registered pytest markers (`network`, `slow`, `models`, `privacy_critical`) + structural-invariant tests gating every PR (silent-except invariant, layering invariant, paired-write inverse-check, etc.). The 4 informational-mode gates (`mypy` permissive / `ruff format --check` first-rollout / `pip-audit` first-pass baseline / Trivy `exit-code: 0` SARIF-only) stay non-blocking; tightening to `--strict` / fail-on-finding is flagged as a post-P1 deferred-tightening candidate, NOT P1 scope.
- **P0.X — brain.db ↔ Kuzu cross-write divergence**: tracked in `complete-plan.md`. brain.db is authoritative; Kuzu is derived state. A crash between a brain.db write and the corresponding Kuzu write leaves the graph stale. Heals on next `_ensure_graph_sync()`, but no detection or alerting exists.

### Issues from issues_to_work.md still pending
- **#28**: Per-person detected language (deliberately skipped — English-only for now)

### Features pending
- **Part 2 Components 1–3 (deferred)**: Remove `_cur_pid` singular primary model; `conversation_turn()` multi-speaker signature; interleaved history with speaker tags. (Phase 3B partially addresses via ROOM block + N-speaker transcript; full migration deferred.)
- **Cross-person excerpts deletion (3B.1.1 cleanup)**: After live multi-person canary validates ROOM block sufficiency, delete `_build_cross_person_excerpts` per reviewer's plan.
- **Token + cost telemetry (S116 P1 #5 deferred)**: Per-call response.usage parsing across multiple API paths — invasive, deferred to dedicated session.
- **Kuzu v3 schema bump**: graph-side `privacy_level` (deferred from S107 audit; reviewer ruled SQL filter sufficient for now).
- Dashboard enrollment camera conflict — `/api/enroll` route conflicts with pipeline.py camera
- Add openWakeWord — push-to-talk wake word, reduces idle resource usage
- Design core/robot.py — hardware abstraction layer before hardware arrives
- Jetson deployment — faiss-cpu → faiss-gpu, TensorRT export, systemd service
- ReSpeaker barge-in — re-add `_vad_interrupt_listener` when ReSpeaker 4-mic hardware arrives

---

## Methodology — structured audits vs reactive patching

Reactive patching surfaces ~30% of an invariant's violations.
Structured audits surface ~100%.

Established empirically by P0.4 (silent excepts: 22 sites surfaced via AST audit vs reactive findings) and confirmed by P1.A1-slice (9 layering violations: 7 new beyond the 2 previously known reactively, a 4.5× discovery ratio).

Implication for P1 architectural work: when an invariant is worth enforcing, schedule the structured audit. Don't budget the work as "fix the reactive findings and call it done." When in doubt, audit; don't react.

Future P1 items where this matters most: P1.A4 (service decomposition), P1.A8 (single SQLite split), and any future invariant that scans for boundary violations.

Every behavior-change P0/P1 cycle has a mandatory Phase 0 with grep-verified findings reported BEFORE any test code is written. Skip this and the rework cost exceeds the Phase 0 cost. Validated empirically across P0.2/P0.3/P0.4/P0.5 — each Phase 0 saved 4-6 hours of Step 1 rework.

**Inverse-check discipline (P0.5 empirical validation):** When a structural invariant uses an enumerated method tuple (`PAIRED_WRITE_METHODS`, `VOICE_GALLERY_METHODS`, etc.), ALWAYS pair it with an inverse check. Forward check: every method in tuple follows the pattern. Inverse check: every method matching the pattern IS in the tuple. Without the inverse, a future method that doesn't get registered silently slips through. P0.5 validated empirically: `test_all_paired_write_sites_are_in_tuple()` (AST scan for FAISS write markers) caught `prune_outlier_embeddings` as a real violation — bare `_conn.commit()` + `_rebuild_faiss()` with no lock, no transaction, no sentinel — that would have shipped as production code. "+30 min for inverse check" caught a 7th bug from one P0 cycle. Carries forward to every future PAIRED_WRITE_METHODS-style invariant including P0.X's Kuzu equivalent.

---

## Layering wrapper conventions

When pipeline.py needs access to a core class's owned state, the owning class exposes:

- **Property** — for read-only state exposure with no side effects.
  Example: `BrainOrchestrator.brain_db` (returns the held BrainDB instance).
- **Method** — for side-effecting operations.
  Example: `FaceDB.close()` (idempotent close with `# CLEANUP:` annotation inside).

Don't refactor properties to `get_X()` methods. Property semantics correctly reflect "expose owned state"; method semantics correctly reflect "perform action."

Both shapes are codified in `tests/test_layering_invariants.py::FORBIDDEN_LAYERING_ACCESSES` as the patterns the structural invariant test rejects.

---

## Coding Standards

- No changes without Jagan's explicit go-ahead. Discuss first, always.
- Don't over-engineer. Only make the change requested — nothing else.
- Never silent `except Exception: pass` — always log at minimum.
- No new utility modules for one-off functions. Inline it or add to the most relevant existing module.
- All blocking I/O → `loop.run_in_executor(None, fn)`.
- All settings → `core/config.py` only. No hardcoded magic numbers elsewhere.
- `add_embedding()` return value must be checked at all call sites.
- `delete_person()` always rebuilds FAISS — never call `_conn.execute` DELETE on embeddings directly.
- Close DB connections in tests: `db._conn.close()` before tmp dir cleanup.
- Run `pytest` after every batch of changes. Confirm full suite passes before session end (1273 as of Session 118).
- **No test may touch real production paths.** Tests that exercise destructive operations (`wipe_all`, file deletes, schema migrations, DB inits with default paths) MUST monkeypatch the relevant module-level path constants (`core.db.DB_PATH`, `BRAIN_DB_PATH`, `FAISS_INDEX_PATH`, `GRAPH_DB_PATH`, `FACES_DIR`) to a `tmp_path`. If a test comment says *"can't redirect without monkey-patching"* — that's a bug, not a documented limitation. Fix it before merging. **Historical bug (Session 122, 2026-04-28):** the original Spec 1 acceptance test for "factory reset doesn't touch classifier DB" called the real `wipe_all()` against the real `faces/` dir and silently deleted enrolled-face data, conversation history, brain.db, and Kuzu graph on every pytest run for several days. After the fix, the test still verifies the same property (classifier DB survives) but with zero side effects on production.

---

## Intent Classifier Behavior (Session 80 observations)

- **Implicit shutdown phrases** (e.g. "goodnight, I'm heading to bed") classify as `casual_conversation`, NOT `request_shutdown`. **By design** — shutdowns require explicit phrasing ("shut down", "turn off", "power down"). Session 80 observation documented as intended behavior; the conservative classifier + strict intent-match gate produces the safer outcome (no implicit shutdowns). Users who want the AI to stop must phrase explicitly.
- **"Unclear" escape hatch leaks at ~10%**: Llama-3.3 occasionally picks a specific (wrong) label with low confidence instead of routing to `unclear` per the CRITICAL directive. Not worth another prompt-tuning pass — the confidence floor (0.75 general, 0.80 shutdown) catches these regardless. Dual-gate design is robust to this failure mode.
- **Cyrillic homoglyph handling**: NFKC normalization in `_intent_allows()` does NOT alias Cyrillic а (U+0430) to Latin a (U+0061) by design. If the classifier extracts a spoofed variant AND the tool_args use the same spoofed variant, grounding fails against the user_text (Latin). Correct behavior — reject code-point mismatches in tool actions.

---

## Pyannote vendoring (P0.R5, 2026-05-23)

Pyannote 3.3.2 + speechbrain 1.0.3 ship as forked git repos under the `HungryFingerss` GitHub organization. The 7 patches that previously required runtime application via `tests/patch_pyannote_io.py` (deleted at P0.R5 closure) now live directly in the fork commits.

**Forks:**
- `github.com/HungryFingerss/pyannote-audio` @ `4978441ee45d1feaea6ce7db7ccf5e67f76a31f8` (3.3.2 base + 9 patches: P0.R5 6 [torchaudio 2.9+ compat + huggingface_hub kwarg + weights_only] + Pre-P1 Bundle 1 3 [pkg_resources→pkgutil.extend_path in pyannote/__init__.py + obsolete setuptools>=38.3 check removal in setup.py + pyscaffold setup_requires removal in setup.cfg; all for setuptools>=81 compat])
- `github.com/HungryFingerss/speechbrain` @ `a9b05847aca696b7eb28dd47c6276afcb2bc14d4` (1.0.3 base + 1 patch: torch_audio_backend list_audio_backends rewrite)

Both forks live on the `dog-ai/<version>-patches` branch off the corresponding upstream version tag. Branch lineage stays clean off the tag so upstream merges are mechanically rebaseable.

**Dependency declarations** (in `requirements.txt`):

    pyannote.audio @ git+https://github.com/HungryFingerss/pyannote-audio.git@4978441ee45d1feaea6ce7db7ccf5e67f76a31f8
    speechbrain @ git+https://github.com/HungryFingerss/speechbrain.git@a9b05847aca696b7eb28dd47c6276afcb2bc14d4

Pip resolves both git URLs at install time and pins the exact SHA. No more post-install patch script required.

**Patches carried by the pyannote fork (P0.R5 6 patches + Pre-P1 Bundle 1 3 patches = 9 distinct patches; P0.R5 6 were originally Patches 1+2+3+3-cont+5+6+7 in the deleted `tests/patch_pyannote_io.py`):**

| File | Patch | Reason |
|---|---|---|
| `pyannote/audio/core/io.py` | `-> torchaudio.AudioMetaData:` → `-> object:` | Type annotation only; class removed in torchaudio 2.9 |
| `pyannote/audio/core/io.py` | `torchaudio.list_audio_backends()` → `getattr(…, lambda: ['sox_io'])()` (2 sites) | API removed; our audio path is in-memory tensors |
| `pyannote/audio/core/pipeline.py` | `use_auth_token=use_auth_token,` → `token=use_auth_token,` | huggingface_hub kwarg rename |
| `pyannote/audio/core/inference.py` | same kwarg rename | same reason |
| `pyannote/audio/core/model.py` | same kwarg rename × 2 sites | same reason |
| `pyannote/audio/core/model.py` | `weights_only=False` to `pl_load(...)` + `Klass.load_from_checkpoint(...)` | torch 2.6+ default flip; pyannote checkpoints are HF-gated (trusted source) |
| `pyannote/audio/tasks/segmentation/mixins.py` | `from torchaudio import AudioMetaData` → try/except stub | Import must not crash; stub only hit on training path (we run inference) |
| `pyannote/audio/utils/protocol.py` | same `list_audio_backends()` fallback | same cause, different file |
| `setup.py` (Pre-P1 Bundle 1, 2026-05-28) | DELETED `from pkg_resources import VersionConflict, require` import + DELETED obsolete `require("setuptools>=38.3")` check | setuptools >= 81 (2025-07-22) removed pkg_resources from auto-install; pip's isolated build env hits ModuleNotFoundError at setup.py line 5 → wheel build fails. The setuptools>=38.3 check itself is obsolete (released 2018, long pre-dates Python 3.9 minimum). Modern PEP 517 build envs handle build-system setuptools via pyproject.toml. |
| `pyannote/__init__.py` (Pre-P1 Bundle 1, 2026-05-28) | `__import__("pkg_resources").declare_namespace(__name__)` → `from pkgutil import extend_path; __path__ = extend_path(__path__, __name__)` | Stdlib-only namespace package declaration; semantically equivalent. Required for RUNTIME compatibility with setuptools >= 81 venvs (where pkg_resources is no longer auto-available). |
| `setup.cfg` (Pre-P1 Bundle 1 follow-up, 2026-05-28) | REMOVED `setup_requires = pyscaffold>=3.2a0,<3.3a0` declaration | pyscaffold imports pkg_resources via entry_points; when setuptools' egg_info command runs walk_revctrl() in modern build envs (setuptools >= 81), it enumerates all installed entry_points and tries to load pyscaffold's, which fails. pyscaffold is a project-template / maintenance tool for the pyannote authors — NOT required to build the wheel. setup() in setup.py uses setuptools.find_packages directly. |

**Patch carried by the speechbrain fork (1):**

| File | Patch | Reason |
|---|---|---|
| `speechbrain/utils/torch_audio_backend.py` | `torchaudio.list_audio_backends()` → `getattr(…, lambda: ['sox_io'])()` (2 sites) | speechbrain imports torchaudio → crash at module load without this |

**Upstream-merge procedure** (when pyannote or speechbrain releases a new version):

1. `git fetch upstream` in the fork repo
2. `git merge upstream/main` (or target tag)
3. Manually re-apply the dog-ai patches (rebase onto upstream changes)
4. Commit + tag the new patched commit
5. Bump SHA in `requirements.txt`
6. Run `pip install --force-reinstall --no-build-isolation -r requirements.txt`
7. Verify `from pyannote.audio import Pipeline` works without any runtime patch
8. Run `pytest tests/test_p0_r5_vendor_forked_pyannote.py` to confirm all 9 anchors still pass

**Install-time gotcha:** speechbrain 1.0.3's `setup.py` imports `pkg_resources`, which `setuptools>=81` removed by default. Install with `setuptools<81` in the venv OR pass `--no-build-isolation` so pip's build env inherits the venv's older setuptools. The error surfaces as `ModuleNotFoundError: No module named 'pkg_resources'` during the speechbrain wheel build.

**GitHub-availability assumption + operator mitigation:**

External forks create a deployment dependency on github.com availability + fork-repo persistence. If GitHub goes down or a fork is accidentally deleted or made private, `pip install -r requirements.txt` will fail with a git clone error.

Mitigation: operators should maintain a local clone of each fork on the production host. If a fork repo is lost, re-create from local clone + push to a new URL + bump SHA in `requirements.txt`. For multi-host deployments, consider mirroring forks to a self-hosted git server or vendoring source directly (future P0.R5.X follow-up if the pattern recurs).

**Out-of-scope at P0.R5 — kept in `core/voice.py` runtime wrapper:**

`core/voice.py::load_speaker_embedder()` retains a runtime `hf_hub_download` wrapper that strips `use_auth_token=` from speechbrain's internal calls. Speechbrain 1.0.3 still passes the removed kwarg; the wrapper transparently pops it before delegating. This patch was NOT in the deleted `tests/patch_pyannote_io.py` and is NOT in the speechbrain fork — it's a runtime-only workaround that survives P0.R5 by design. Future cycle may move it into the speechbrain fork.

**Fallback (if forks stale + patches don't apply to a new upstream):**

SpeechBrain's built-in spectral-clustering diarization recipe is the Option D fallback per Session 88. SpeechBrain is already in our venv for ECAPA-TDNN; the recipe trades off ~2-3 percentage points of DER worse than pyannote but eliminates the upstream-compat brittleness.

**Pinned version:** `pyannote.audio==3.3.2` + `speechbrain==1.0.3`. Do NOT bump to pyannote 4.0.x without re-evaluating torchcodec/FFmpeg viability on dev+Jetson.

---

## Classifier graph (Spec 1, 2026-04-27)

The pure-graph classifier's data foundation. Lives at `data/`, separate from `faces/` — system intelligence, NOT personal data. Spec 2 (the actual graph classifier) consumes it; Spec 1 just builds the seed.

**Files:**
- `core/classifier_db.py` — schema, migrations, audit log, read/write API. Single source of truth for all writes.
- `data/classifier_scenarios_seed.jsonl` — committed to git. Built once via the bootstrap pipeline; ships with KaraOS.
- `data/classifier_scenarios.db` — gitignored. Built from seed on first boot (Spec 2's responsibility). Accumulates live outcome supervision data.
- `data/classifier_audit_log.jsonl` — gitignored. Per-deployment append-only log of every counter change / quarantine.
- `data/classifier_snapshots/` — gitignored. Daily backups, 30-day retention.
- `bootstrap/classifier/` — 6-stage offline pipeline + ~100 hand-authored scenarios + run_all orchestrator. Run once, manually, with `TOGETHER_API_KEY` set. ~$1.05 cost, ~15-20 min. Read `bootstrap/classifier/README.md` for the run procedure.

**Factory-reset semantics (load-bearing):**
- `core/db.wipe_all()` ONLY touches `faces/` and `sim_session_state.json`. The `data/` dir is intentionally outside its scope.
- A factory reset wipes who-Jagan-knows. The classifier graph is what-the-system-has-learned-about-language; that survives by design.
- Test `test_factory_reset_does_not_touch_classifier_db` enforces this invariant.

**What's in the seed (post-bootstrap):**
- ~1,500-1,700 abstracted scenarios from Cornell Movie-Dialogs + DailyDialog + EmpatheticDialogues, classified by 70B into the production label space, name+place stripped via spacy NER, embedded via E5.
- ~100 hand-authored scenarios (`bootstrap/classifier/hand_authored_scenarios.py`) covering the 10 high-stakes intent categories from Sessions 71-117 (request_shutdown, question_about_shutdown, assign_*_name, confirm_identity, deny_identity, live_data_query, general_knowledge_query, casual_conversation, direct_address_to_person).
- All embeddings dim-1024 float32 from `intfloat/multilingual-e5-large-instruct`. Embedding model ID is locked in `db_metadata`; switching models requires a re-embed pass (see Spec 1's "embedding model versioning" notes).

**Held out (DO NOT add to bootstrap):** Friends, AMI, MELD, EmotionLines. Including them would leak into `published-papers-tests/` benchmarks.

**Schema versioning:** `schema_migrations` table tracks every applied migration. `label_evolution` table maps deprecated labels at query time. `active` column quarantines bad rows instead of deleting. `audit_log` is append-only.

Continuous-evaluation tooling on top of the bench harness (S82), golden corpus (S81), and `intent_divergences` table (S85). Pure observability — none of this affects production behavior.

### Weekly (every Monday)

```bash
python tests/eval_weekly.py
```

Runs the golden-set bench, persists the run, and compares to the most recent prior run. Queries `intent_divergences` for the last 7 days (configurable via `EVAL_WEEKLY_DIVERGENCE_LOOKBACK_DAYS`). Prints a markdown report covering: per-intent precision/recall drift, top low-confidence gate decisions, recent rejections (for false-reject review), and shadow samples (`mode='shadow'`).

Add `--alert` to exit non-zero when any per-intent precision drops by `EVAL_WEEKLY_ALERT_PRECISION_DROP_PP` percentage points or more (default 5.0). Suitable for cron / CI integration.

Action items: if any per-intent precision drops by ≥5pp, investigate before the next live session.

### Quarterly (every ~3 months)

```bash
# Step 1: export 20 random stratified golden rows for review
python tests/golden_set_drift.py --mode export

# Step 2: review the exported markdown manually (15-30 min)

# Step 3: feed the filled markdown back
python tests/golden_set_drift.py --mode compare \
  --filled tests/golden_set_drift_YYYY-MM-DD.md
```

Detects whether stored ground-truth labels are still correct as user phrasings + the world evolve. Drifted rows get either a re-label, a `regression_session_<n>_relabel` companion row, or marked `legacy_synthetic` if obsolete. **Drift detection is a judgment call** — the script just makes the human review efficient.

### After every live canary

Inspect new `intent_divergences` rows since last review. Specifically:

- Any `mode='gate' AND gate_decision LIKE 'reject%'` rows: was the rejection correct?
- Any new patterns in `mode='shadow'` samples (1% of production turns sampled passively): did the classifier behave honestly on edge cases?
- Add new rows to `tests/golden_intent.jsonl` for any divergences worth preserving as regression guards (tag `regression_session_<n>`).

### Canary shadow sampler

`pipeline.conversation_turn` calls `_classify_intent` on a 1% canary sample of every turn (gated by `SHADOW_SAMPLE_RATE` + `SHADOW_SAMPLE_ENABLED` kill switch) and writes the result to `intent_divergences` with `mode='shadow'`. This catches drift on turns that never trigger a tool gate. Wrapped in try/except so a sampling failure can't break a turn — production behavior is unaffected by shadow-mode failures.

To disable temporarily: flip `SHADOW_SAMPLE_ENABLED = False` in `core/config.py`.

---

## Classifier graph (Spec 2, 2026-04-28) — pure-graph classifier + online learning

Spec 2 ships the actual graph classifier on top of Spec 1's seed. NO LLM call in the classification hot path. NO LLM call in the correction-detection path. NO LLM call in outcome supervision.

**Files:**
- `core/classifier_graph.py` — `classify_intent_graph()` (abstract → embed → top-K cosine k-NN → Wilson lower-bound vote → de-abstract → sidecar). Same return shape as `_classify_intent`. Handles correction loop via `handle_correction()` + `extract_correction_target()`. Module-level `_pending_outcomes` deque + `record_pending_outcome` / `confirm_pending` / `revert_pending` / `age_pending_outcomes` for the 3-turn outcome supervision window.
- `core/abstraction.py` — production-time two-pass abstraction (registry-first, then spacy NER fallback). Times/dates/numbers preserved. Module-level spacy singleton.
- `core/classifier_db.py` v2 schema — `extracted_value` column on scenarios table. Idempotent `ALTER TABLE` migration; existing v1 DBs upgrade in place.
- `core/brain.py::_classify_intent_smart` — three-stage orchestrator routing shadow/primary/retired modes per `GRAPH_CLASSIFIER_MODE` config flag.
- `pipeline.py` — `age_pending_outcomes()` called once per turn (no-op when queue empty); correction-skip-brain branch when sidecar emits `correction_to_previous_response` (calls `handle_correction` and returns without generating brain response — LLM-free path).

**Modes:**
- **shadow (default after ship)** — both classifiers run in parallel; LLM result drives behavior; graph divergences logged via `[Intent] shadow divergence` stdout. Production behavior unchanged.
- **primary** — graph fires first; if `confidence >= GRAPH_PRIMARY_CONFIDENCE_FLOOR` (0.55) return graph; else fall back to LLM safety net. Graph decisions enter the outcome supervision queue.
- **retired** — graph only; LLM never called. If graph abstains (confidence below `GRAPH_ABSTAIN_THRESHOLD=0.40`), classifier returns None and the gate code falls back to default-silent.

**Cutover discipline:** never all-at-once. Ship in shadow, observe divergences for 1-2 weeks of live use, target <5% divergence rate on routine traffic before flipping to primary. Primary mode validates over weeks before flipping to retired. The old `_classify_intent` LLM classifier stays in the repo as the safety net during primary mode.

**Wilson lower-bound aggregation** — a single confirmation does NOT get full credit. `confidence_score` returns the 95% CI lower bound of the confirmation rate, smoothed by initial_confidence when no outcome data exists. Prevents single-correction events from over-skewing the graph.

**Correction loop (LLM-free):**
1. Classifier emits `correction_to_previous_response` (bootstrapped intent, 30 hand-authored examples + 5 negative discriminators in seed).
2. Pipeline detects label, calls `handle_correction(text)` → `latest_pending()` → decrement scenarios that voted for the wrong label on turn N-1.
3. Regex bank (`_DEFAULT_CORRECTION_PATTERNS_TEMPLATE`, ~14 patterns) extracts intended target. Patterns capture pronouns ("you" / "me") get filtered out as decrement-only signals.
4. If real target name extracted: re-abstract turn N-1's user_text with the corrected target, embed, insert as `direct_address_to_person` scenario with `source_tag="live_correction"` + `initial_confidence=0.85`.
5. Brain stays silent — no "sorry, my mistake!" response that would be additional intrusion. Pipeline returns `("continue", None)` early.

**Latency:** the spec's 100ms p95 target is achievable on the local-only path (abstraction + cosine k-NN + aggregation), validated by `test_classifier_graph_latency_under_budget` over a stubbed-embedding fixture. Real production latency depends on the embedding service (Together.ai E5 endpoint, ~300-500ms per call). Future optimization candidates: local E5 model, ANN index in place of brute-force cosine, spacy doc cache.

**Validation gate before primary cutover:** re-run the Qwen-7B + Llama-70B Friends benchmarks with the graph classifier in place. Both numbers should converge — proves the architecture is genuinely model-agnostic. Pre-Spec-2 baseline: Llama-70B+LLM-classifier=58.66%, Qwen-7B+LLM-classifier=52.32% (the divergence that motivated the architecture pivot).

**Tests (1314 = 1294 + 20):** see `tests/test_classifier_graph.py` — output shape, no-LLM-calls in classifier hot path, no-LLM-calls in correction path, abstain on conflicting graph, Wilson formula, abstraction PERSON/LOC/times-preserved, correction decrements + new-scenario writes + null-target handling, 3-turn outcome supervision auto-credit, shadow/primary/retired mode routing, latency p95 under budget.

**Operator hooks:**
- `core.classifier_graph.aclose()` — close singletons on shutdown (httpx client, ClassifierDB connection).
- `core.classifier_graph.reset_pending_outcomes()` — clear the queue (factory reset / test setup).

---

## Golden Intent Set (P1.5, Session 81) — source taxonomy + deprecation rule

Golden corpus lives at `tests/golden_intent.jsonl`. Schema per row:
`user_text`, `expected_intent`, `expected_value`, `source`, `note`
(plus optional `observed_intent` / `observed_value` / `observed_conf` / `source_file` for `real_observed` rows).

**Source taxonomy (fixed upfront — tests enforce):**
- `real_observed` — harvested from archived terminal_output logs via `tests/harvest_golden.py`, hand-labeled by a human.
- `adversarial` — from the locked VISION_ROADMAP 1.9 list (Detroit, Kara, homoglyph, injection, implicit-shutdown, etc.). **Regression-permanent — never deprecated.**
- `synthetic_common` — hand-written templates, each traced to a specific bug class in the Completed Sessions table. Deprecated once `real_observed` per intent reaches the threshold (see rule below).
- `regression_<session>` — bug caught in production, labeled with the session number. **Permanent.**
- `legacy_synthetic` — the post-deprecation state of a `synthetic_common` row. Retained in file as historical record; **excluded from precision/recall computation** so synthetic pairs can't artificially prop up metrics after real data exists.

**Deprecation rule:** when a given intent has ≥25 `real_observed` rows, all `synthetic_common` rows for that intent flip to `legacy_synthetic`. They stay in the JSONL but the eval bench (P1.6) filters them out of metric aggregation. Without this rule, synthetic pairs would silently distort precision numbers long after real data is available; drift detection would become meaningless.

**P1.6 → P1.7 wire-in gate (two conditions, not one):**
1. Hybrid-set (all non-legacy rows): per-intent precision ≥ 0.95, recall ≥ 0.85, ECE ≤ 0.05
2. `source=real_observed` subset alone (≥30 rows total, across intents): same thresholds

A single-gate on the hybrid set would green-light a validator that only looks good because `synthetic_common` was engineered to pass. The real-only gate is the anti-cheat.

**Current corpus (Session 87 end):** 149 rows — 3 `real_observed`, 60 `adversarial`, 77 `synthetic_common`, 6 `regression_session_82_relabel`, 3 `regression_session_86`. All 12 `INTENT_LABELS` represented. Shutdown-family (`request_shutdown` + `question_about_shutdown`) and `deny_identity` each have ≥25 rows (high-blast-radius floor enforced by `test_golden_intent_jsonl_high_blast_radius_min_coverage`).

**`regression_session_82_relabel` tier explained:** these 6 rows came out of the Session 82 bench run where the classifier was CONSISTENT and the GOLDEN labels were wrong (5 out-of-context confirm_identity affirmations + 1 correction phrasing). Distinct provenance from `regression_<session>` (production bug) — both permanent, both excluded from the deprecation rule, but the tier name encodes the reason for permanence. Use `regression_<session>_relabel` suffix for future calibration relabels.

**Archive hook:** `pipeline._archive_terminal_output()` at pipeline startup renames the prior `terminal_output.md` to `terminal_output_YYYY-MM-DD_HHMMSS.md` (using the file's mtime). Collision-safe. This is the P1.5 data-accumulation machinery — every live session now produces a named, preserved archive that the harvest script can parse into new `real_observed` rows.
- Update this file at session end. Verify all values against source code before writing.

---

## Hardware Targets

| Target | Status |
|---|---|
| Windows 11 laptop | Current dev — DirectShow camera, CUDA |
| Jetson AGX Orin 32GB | Production target — V4L2, faiss-gpu, TensorRT |

Jetson checklist (when ready):
- `pip install faiss-gpu` instead of faiss-cpu
- Confirm buffalo_l auto-downloads (~500MB) or pre-copy
- CUDA 12.x + cuDNN 9.x (match onnxruntime-gpu)
- V4L2 backend: auto via `sys.platform != "win32"` check
- `loop.add_signal_handler(SIGTERM, ...)` works on Linux (not Windows)

---

## Session Protocol

**Starting a session:**
1. This file is auto-loaded — read it first.
2. Check test count at top.
3. Run `pytest` to confirm green state.
4. Discuss what to work on before touching any code.

**Ending a session:**
1. Update test count line at top.
2. Move completed work from Pending to Completed Sessions table.
3. Update bug status (resolved bugs removed, new bugs added).
4. Verify all config values in this file match actual config.py.
