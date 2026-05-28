> **CHAPTER 19 — Architectural Disciplines + Upcoming Work** | Sourced from `everything_about_system.md` §322-340 (verbatim mechanical extraction per Plan v2 §1.6 section-number stability invariant).

---

## 322. Induction-Surfaces-Invariant-Gaps

**Track record: 7-for-7** (P0.6.7v2, P0.8.2, P0.11, P0.12, P0.12.1, P0.0.7 ×2).

Every structural invariant ships with an **induction protocol** that deliberately exercises the failure mode the invariant is meant to prevent. The induction is a test of the invariant, not of the production code. When induction surfaces a gap (either in the invariant's coverage or in production code), the gap is closed in the same cycle, not deferred.

The operational rules:

1. Every new structural invariant gets a deliberate-regression check before sign-off — induce the violation, confirm the test fires, revert, document the outcome in the closure report.
2. Mid-flight production fixes from induction findings are NOT scope creep — they are the protocol working. Document them in the same sub-PR.
3. When induction surfaces a detector gap (the invariant didn't catch a real violation), strengthen the detector in the same cycle. Do not defer.
4. Property-based testing (Hypothesis) is a first-class induction tool. Use `max_examples=1000` for contract surfaces.

The 7 instances:

- **P0.6.7v2** — 8 deliberate-regression checks induced field-drift / unenumerated-writer / paired-write-atomicity / producer-copy / peek-not-mutate / ratchet / M2-coverage / prior-state-guard violations; all 8 fired correctly.
- **P0.8.2** — F1 + F2 deliberate-regression: injected sync `.execute()` loop without checkpoint + flipped `include_tools=False` → `True`; both invariants fired correctly.
- **P0.11** — 3 deliberate-regression checks; the third surfaced a detector gap (attribute-form access not caught) → detector strengthened in same cycle.
- **P0.12** — Hypothesis property tests (1000 examples/test) induced two real production bugs.
- **P0.12.1** — caller-audit surfaced one real downstream regression (`SocialGraphAgent` list-shape branch became unreachable after P0.12); fix landed in same cycle via sibling `_parse_json_array`.
- **P0.0.7 (instance 1)** — round-trip test's coverage gate caught `presence_state` missing from fixture scenarios → added to scenario B in same cycle.
- **P0.0.7 (instance 2)** — full-suite verification caught 12 P0.4 silent-except violations the subset-verification missed → fixed via `safe_emit_sync` consolidation.

## 323. Architect-Reads-Production-Code-Before-Sign-Off

**Track record: validated across P0.6.7 v1→v2, P0.7 closeout caller audit, P0.12.1 audit.**

Reviewer / auditor sign-off requires reading the actual implementation against the closure summary. Summaries describe intent; code reveals what shipped.

Three documented instances:
- **P0.6.7 v1→v2** — three real gaps surfaced by post-closure audit: vision-globals migration miss, CacheStore touch-on-read LRU violating the locked spec, 4th-shim miscounted disclosure.
- **P0.7 closeout caller audit** — 187 legacy patterns in `test_pipeline.py` surfaced after the 1717-passing milestone was reached.
- **P0.12.1** — Site B dead branch surfaced from post-closure caller audit; Site A flagged but actually safe under existing dual-guard.

The architect's read pass before sign-off is cheap (~30 minutes of focused diff review) and catches the cases where the closure summary diverges from what shipped. This is *complementary* to the developer's verification — it's not redundant; it's a different kind of pass against a different question.

## 324. Verification-Before-Completion (Strengthened by Full-Suite Lesson)

When about to claim work is complete, fixed, or passing, before committing or creating PRs — run verification commands and confirm output before making any success claims. **Evidence before assertions, always.**

P0.0.7 Step 5 polish strengthened this discipline. The original claim "no regressions" was based on subset verification (P0.10 + reconciler + event_log tests). Reviewer's full-suite verification caught 12 P0.4 silent-except violations the subset verification missed. The lesson banked: subset verification is necessary but not sufficient; always run `pytest --tb=no -q` (full suite) before "no regressions" claims. The full-suite cost on this codebase is ~163 seconds; the cost of a wrong "no regressions" claim is much higher.

## 325. Spec-First Review Cycle for Multi-Day Specs

**Track record: 5-for-5** (P0.6, P0.7, P0.8, P0.9, P0.10).

For sub-PRs estimated > 1 day, the workflow is:

1. **Phase 0 audit** — pure documentation, zero production-code changes, grep-verified findings reported BEFORE any test code is written.
2. **D1-Dn decisions surfaced** in the audit document.
3. **Architect / auditor sign-off locks them** before Plan v1 is drafted.
4. **Plan v1** is the first complete spec.
5. **Architect / auditor feedback drives Plan v2.**
6. **Code phase** starts only after v2's locked structure is in place.

Spec-time investment pays back 2–4× in mid-flight rework avoided — every cycle that skipped Phase 0 hit larger surprises. The empirical proof: every Phase 0 audit in P0.2 – P0.10 saved 4–6 hours of Step 1 rework. The compound win across multi-day specs is substantial.

P0.0.7 added a 6th instance to the cycle in 2026-05-18 (Phase 0 audit at `tests/p0_07_event_boundary_audit.md` → Plan v1 → Plan v2 with R1-R5 refinements → 8 implementation steps). Track record refresh pending the next multi-day spec.

## 326. Spec-Contracts-Not-Implementations

**Track record: 3-for-3 (P0.8.2 F2, P0.9.1, P0.9.2).**

Architect specs describe what invariants must hold (the contract), not how to satisfy them (the implementation). Developers find the best implementation within the contract.

Why it matters: the developer has full visibility into the actual code, runtime state, surrounding patterns, and adjacent constraints the spec author cannot pre-load. Specs that lock contracts let the developer's local knowledge improve the mechanism; specs that lock mechanisms turn the developer into a transcription typist.

Examples of contract vs implementation:

- **Contract**: "every paired-write site must use a `_mark_X_dirty()` sentinel before the cross-storage write."
- **Implementation**: which file, which exact name, which line — developer's call.

- **Contract**: "the band-divergence trigger fires when `utt_band ∈ {gap, short_hard}` and the rule that fired isn't the band's expected rule."
- **Implementation**: where the mapping lives, what data type — developer's call (this is P0.10.1 F2: `EXPECTED_RULES_BY_BAND` belongs in `core/reconciler.py`, not pipeline.py inline).

## 327. Developer-Improves-on-Spec-by-Reading-Carefully

**Track record: 5-for-5.**

When implementation reveals a better path that preserves the spec's architectural intent, bank the improvement explicitly in the closure report so the architect / auditor sees the deviation + rationale.

The 5 instances:

- **P0.8.2 F2** — spec named external call sites; developer's caller audit found the actual contract was internal (`ask_retry_text` doesn't accept `include_tools` as a parameter by design), so F2 verified the internal contract instead.
- **P0.9.1** — spec sketched a fresh `init_ledger()`; developer made it self-evolving (idempotent ALTER adding `is_initial` to pre-P0.9 ledgers) so the classifier_scenarios.db schema upgrade rode the same code path.
- **P0.9.2** — spec defined 4-tuple migrations; developer split `verify_post`/`verify_present` because conflating them would let bootstrap stamp `is_initial=1` on a partially-backfilled DB.
- **P0.10 Block C** — spec said "extend the existing divergence-log block with more fields, don't change trigger"; Step 7's legacy deletion makes the original trigger unworkable; developer retargeted to band-divergence detection, preserving Block E's gate criteria semantically.
- **P0.0.7 Step 5 polish** — reviewer's P0.4 remediation said "annotate the 12 hook-site try/except blocks with `# OPTIONAL:`"; developer instead consolidated to a single `safe_emit_sync(...)` helper with one annotated except. 12 violations → 1 annotated except + 12 unannotated call sites. Strictly better than the annotation patch the reviewer proposed.

Pairs with **spec-first review cycle** (the discipline that produces these moments) and **spec-contracts-not-implementations** (the architect-side framing that makes them welcome).

Sub-patterns identified:

- **Sub-pattern A (premise correction)** — P0.10 Phase 0 audit caught the architect's wrong premise about Bug-W living in legacy when it actually lived in the new reconciler. Different shape from mechanism-level improvement: the audit changes WHAT gets built, not just HOW.
- **Sub-pattern B (developer resists premature pattern elevation)** — P0.0.7 plan v2 discussion. Architect proposed elevating "tripwires must match the actual deferral surface" to a CLAUDE.md named doctrine after 4 instances. Developer pushed back: the established cadence is "3+ instances → memory note; 5+ instances → CLAUDE.md named doctrine" per the P0.10.1 F3b pattern. At 4-for-4, pattern is memory-note-only; wait for the 5th instance before elevating. Auditor endorsed the pushback.

## 328. Tripwires-Must-Match-the-Actual-Deferral-Surface

**Track record: 3-for-3 (P0.11 `_persistent` global decl, P0.10 Bug-W audit, P0.0 S2 binding).**

When you defer an item and ship a tripwire to make the deferral safe, verify the tripwire actually catches what the deferral leaves unsafe — not just the symbolic version of it. A tripwire that catches the symbolic version while the real surface stays exploitable is **theater**.

The 3 instances:

- **P0.11 `_persistent` global declaration test** — architect's spec'd detector caught bare-name writes; auditor's deliberate-regression check injected attribute-form access; detector was strengthened to catch BOTH shapes.
- **P0.10 Bug-W audit** — architect's premise "the new reconciler is correct, delete the 273-line legacy router" was wrong; Phase 0 audit caught it before code shipped.
- **P0.0 S2 binding tripwire** — architect deferred S2 (dashboard auth) on the framing: "bound to 127.0.0.1, no LAN exposure today"; tripwire asserted absence-of-LAN-bind, but Next.js defaults to 0.0.0.0 when `--hostname` is absent. Dashboard was LAN-accessible right now. P0.0.1 fix added explicit `--hostname 127.0.0.1` AND tightened tripwire to require the flag.

The architect-side discipline at spec-time: write a paragraph titled **"What this tripwire does NOT catch"** that enumerates implicit-default failure modes, alternate-access-path failure modes, and adjacent-behavior failure modes. If any items list a real risk, EITHER tighten the tripwire OR un-defer the item. Honest scoping is the discipline.

## 329. Structured-Audit-vs-Reactive-Patching (Empirical Foundation)

Reactive patching surfaces ~30% of an invariant's violations. Structured audits surface ~100%.

Established empirically by **P0.4** (silent excepts: 22 sites surfaced via AST audit vs ~7 caught reactively, a 3× discovery ratio) and confirmed by **P1.A1-slice** (9 layering violations: 7 new beyond the 2 previously known reactively, a 4.5× discovery ratio).

Implication: when an invariant is worth enforcing, schedule the structured audit. Don't budget the work as "fix the reactive findings and call it done." When in doubt, audit; don't react.

Future items where this matters most: P1.A4 (service decomposition), P1.A8 (single SQLite split), any future invariant that scans for boundary violations.

## 330. Why Each Discipline Has a Track Record, Not a Rule

The disciplines above are not stated as absolute rules. Each one is a **named pattern with a track record**. The track record matters because:

1. **A rule with no track record is theoretical.** Until a pattern has fired across multiple instances, it's a hypothesis. The track record is the empirical evidence that the pattern is real.
2. **A track record is auditable.** Anyone can grep `Track record: N-for-N` and read the actual instances. The pattern's status is visible.
3. **A track record refreshes.** Each new instance adds a notch; each closure cycle adds context. The pattern earns its place as it pays off in practice.
4. **The cadence prevents premature elevation.** Per the P0.10.1 pattern banked as sub-pattern B in §327: 3+ instances → memory note; 5+ instances → CLAUDE.md named doctrine. The cadence is meaningful; it prevents the architect from naming every accident-of-the-moment as a doctrine.

The disciplines above all sit at 3+ instances (one at 5+, several at 4+). New disciplines join when they reach 3 instances; named doctrines elevate when they reach 5.

---

# Part LI — Upcoming Work and Roadmap

## 331. P0.0.7.X — Hypothesis TestLargeInput Flakiness  [CLOSED 2026-05-18]

**Status: CLOSED 2026-05-18.** Self-resolved between filing (P0.0.7 closure) and post-P0.S1 re-verification.

**Phase 0 audit at closure time:** 6-for-6 stability case banked — 3 × full-suite runs (Hypothesis included) at 2302 / 2302 / 2302 passed, plus 3 × Hypothesis file alone at 36 / 36 / 36 passed. No flake reproduction across the 6 independent runs.

**Likely fix mechanism (incidental, not deliberately targeted):**
- P0.S1 Phase 1 autouse-fixture additions: `AntiSpoofRejectionStore.reset` + TrackStore extension reset paths added to the conftest loops.
- P0.0.7 producer-state-reset hooks added incrementally after the original flake observation.
- Test isolation surface is cleaner now than at the time the flake was documented.

**Closure decision:** the file is re-included in default `pytest` runs (`--ignore` flags dropped from the validation runbook and from CLAUDE.md / everything_about_system.md). No deliberate stability tripwire added — the 36 Hypothesis tests are themselves the regression coverage; re-emergence would surface naturally on the next full-suite run.

**If the flake re-emerges in future, file a fresh follow-up rather than re-opening this entry** — the conditions that caused it are gone and any new instance is almost certainly a different mechanism.

## 332. P0.S1 — Anti-Spoof on Every Face Match (Next Item)

**Status: greenlit pending P0.0.7 auditor sign-off. Next item in the locked sequence.**

Pre-P0.S1, anti-spoof is gated on the greeting path (`is_live()` is called in `first_boot_flow` and `enrollment_flow`) but NOT on every face match. The recognition update path (`add_embedding(source="recognition_update")`) writes to the gallery when a high-confidence face match occurs; if that face match was actually a presentation attack (photo, screen, video replay), the attacker can poison the legitimate person's gallery.

Session 51's MiniFASNet activation (Session 52) closed the gating gap on the greeting path. P0.S1 closes the gap on every match.

The architectural approach:
- Every code path that calls `FaceDB.add_embedding(...)` with `source="recognition_update"` must pass through `verify_live(...)` first.
- Replay regression tests built on top of P0.0.7's scenario fixtures (`build_greeting_flow`, `build_stranger_first_encounter`) — the fixtures already capture `anti_spoof_live` and `anti_spoof_score` in `VisionFramePayload`, so the test can pin the assertion at the gate without live camera input.
- The current `ANTISPOOFING_THRESHOLD = 0.5` is the production gate; P0.S1 may tune this empirically but not as part of the structural fix.

Phase 0 audit + Plan v1 + Plan v2 cadence per the spec-first-review-cycle (§325). The replay fixtures unblock the regression tests; the regression tests pin the behavior at the new gate.

## 333. P0 Security — The Locked Sequence Beyond P0.S1

The complete-plan.md security backlog has S1 through S11. The user-locked sequence:

- **P0.S1** — anti-spoof on every face match (next)
- **P0.S6** — secrets management (env vars, no hardcoded API keys)
- **P0.S5** — dashboard CSRF protection (deferred S2 remains pre-auth; S5 is the inside-the-auth-boundary protection)
- **P0 medium-priority security** — S2 (dashboard auth proper), S3 (input sanitisation), S4 (TLS for dashboard), S7-S11 (specific surface hardening)

Each item ships as a Phase 0 audit + Plan v1 + Plan v2 + code cycle. Each one ends with structural invariants + induction-confirmed regression tests.

## 334. P0 Robustness — R1 through R11

The robustness backlog targets failure modes that don't affect security or correctness directly but degrade reliability over time:

- **P0.R1** — startup determinism (every boot from a clean state must reach `WATCHING` within budget; surfaces flakiness in model loading, DB init, etc.)
- **P0.R2** — model cache integrity (HF model downloads can corrupt; checksum verification + redownload on mismatch)
- **P0.R3** — graceful degradation matrix (formal documentation of every degraded mode + recovery path)
- **P0.R6** — DB integrity check on boot (PRAGMA integrity_check on faces.db, brain.db, classifier_scenarios.db; auto-repair if possible, alert if not)
- **P0.R7** — fallback brain when Together.ai unavailable (current: Ollama hardcoded; user has flagged this needs to be config-driven like the primary brain for plug-and-play model swapping)
- **P0.R10** — config snapshot on boot (record the config values that affect this run, for post-hoc debugging)
- **P0.R11** — automated backup of brain.db + faces.db on dream cycle

The expected sequence is R3 → R2 → R6 with an R7 spike in parallel (the user wants deeper discussion before R7's spec lands). R1, R10, R11 follow.

## 335. Eval Gates — Continuous Evaluation Becomes Real

The eval-gates work formalises the continuous-evaluation tooling sketched in Part XXX. The components:

- **Golden corpus** — `tests/golden_intent.jsonl` already exists with 149 rows (Session 87 end). The corpus grows per the source-taxonomy rules in CLAUDE.md.
- **Bench harness** — `tests/eval_intent_bench.py` (P1.6) runs the classifier against all non-legacy rows and persists run metrics + mismatches to `tests/eval_bench_runs/YYYYMMDD_HHMMSS.json`.
- **Weekly drift report** — `tests/eval_weekly.py` queries `intent_divergences` over the last 7 days, prints per-intent precision/recall drift, low-confidence gate decisions, recent rejections.
- **Quarterly golden-set drift detection** — `tests/golden_set_drift.py` exports 20 random stratified rows for human review, accepts the reviewed markdown back, flags drifted labels.

Each tool is a standalone module; none of them block production behavior. The eval gates work makes the metrics surface visible enough that drift can't hide between releases.

## 336. P1.A — Pipeline.py Decomposition into ~30 Modules

`pipeline.py` is currently ~10,000 lines. P0 work has reduced its size somewhat (the Store-pattern migration moved ~3500 lines to `core/store_*` modules) but the file is still the project's single largest module and the bottleneck for understanding the runtime.

P1.A is the decomposition project. The plan (in coarse outline; Phase 0 audit will refine):

- **P1.A1** — layering audit (already done as a slice in P0.X-audit; the full audit will surface every cross-module access pattern)
- **P1.A2-A6** — extract the major runtime services into named modules (microphone capture loop, vision background loop, conversation turn handler, session lifecycle, brain dispatch)
- **P1.A7-A12** — extract the supporting services (KAIROS, dream loop, factory reset, IPC writers, classifier wiring, anti-spoof integration)

Each extracted module follows the Part XXXII pattern: pure functions where possible, structural invariants on import boundaries, AST-enforced layering rules.

Target end state: `pipeline.py` shrinks to roughly 1500-2000 lines of orchestration code; the runtime logic lives in ~30 focused modules under `core/`. The decomposition is the biggest single architectural improvement queued — but it has to land AFTER the P0 security/robustness/eval cycle because those provide the test scaffolding that makes safe decomposition possible.

## 337. Voice Gallery Growth Bug for Promoted Voice-Only Strangers

**Known issue, fix queued.** (Documented in Part XXXII §203.4.)

Session 94 added bootstrap-credit replenishment so engaged strangers could grow their voice profile to maturity. The condition includes `person_type == 'stranger'`. After a voice-only stranger is promoted via `update_person_name` ("My name is Lexi"), the promotion chain flips `person_type` to `known`. The replenishment condition stops firing. Subsequent voice samples are refused.

The fix shape (architect's recommendation, pending implementation):
- Add a `voice_only_origin` session-dict flag, set at engagement-gate pass when no face was witnessed.
- Replenishment fires when `voice_only_origin == True` AND `voice_n < MATURE`, regardless of `person_type`.
- Flag clears on first face-witness event.

Cost: small (10-20 lines + 3 tests). The reason it's not P0.S1-priority is that the failure mode is gradual degradation (stunted voice profiles) rather than active security risk. Will land alongside one of the P0.R items where session-state plumbing is already on the table.

## 338. Kuzu v3 Schema Bump and Graph-Side Privacy

Sessions 96-108 (Phase 3A) shipped the four-tier privacy model and the SQL-side `_visibility_clause` helper. The corresponding Kuzu-side change — gate `find_shared_entities` and similar 1-hop traversals on `privacy_level` — was deferred. The full Kuzu v3 bump will:

- Add `privacy_level` to graph edges.
- Update the `find_shared_entities` MATCH query to filter on `privacy_level != 'system_only'`.
- Wire `room_session_id` and `audience_ids` into conversation_log retrieval paths via graph-aware queries (currently Q3 is SQL-only).
- Rev the `GRAPH_SCHEMA_VERSION` from 2 to 3, triggering rebuild from brain.db on first boot.

Deferred reason: the SQL-side filter is sufficient for current threat model (S107 audit). v3 lands alongside the RoomOrchestrator work (currently scoped under Phase 3B, deferred until P0 cycle is fully closed).

## 339. Format-Bridge Unification (Producer Rows vs CLI Render)

**Open architectural smell from P0.0.7 Step 7.** `ctx.all_events()` returns events with `payload` (parsed dict); CLI's `_render` expects `payload_json` (raw JSON string). Tests bridge with `{**e, "payload_json": json.dumps(e["payload"], sort_keys=True)}` before passing to `_render`.

The bridge is harmless in tests; it's mild architectural debt. A future micro-PR unifies the row dict shape so callers don't need to bridge. Either:

- Producer rows carry both `payload` (parsed) and `payload_json` (raw) — caller picks.
- Producer rows carry only `payload_json` — caller does `json.loads` if they need parsed.
- Producer rows carry only `payload` — caller does `json.dumps` if they need raw.

Decision pending; not blocking other work.

## 340. The Multi-Layer Classifier Architecture (XXXV) — When It Ships

Part XXXV documents the six-layer multi-layer classifier architecture as **FUTURE WORK**. The dependency chain is:

1. P0 security + P0 robustness + Eval gates land (current trajectory).
2. P1.A pipeline decomposition lands (next major architectural project).
3. THEN the classifier multi-layer work can land cleanly because it builds on top of a clean classifier integration point (`classify_intent_smart` → `classify_intent_graph` → the multi-layer graph) without touching the rest of the system.

The work is committed (the Part XXXV roadmap is locked) but the timing is sequential. When P1.A is done, multi-layer can ship in 4-6 weeks.

Until then, Part XXXV is the architectural commitment, not the implementation.

---

# End of Document

This documentation describes the system as of **2026-05-18, post-P0.0.7 event-sourcing foundation, full P0 correctness + architectural-hardening cycle closed, ~2216 tests passing**. It is intended to be read front-to-back by someone learning the project for the first time, and also to be searchable reference material for anyone debugging a specific subsystem.

Further updates should preserve the pattern: every design decision traces to a specific incident (logged in `CLAUDE.md`), a specific config value, or a specific architectural principle from Part XXII or Part L.

If you add a new subsystem, write its section before writing its code. If you change a threshold, update §147. If you land a new agent, extend Part XIV. If you discover an invariant that isn't in Part XXII or named in Part L, add it. If you complete a multi-day spec, add an instance to the appropriate track record in Part L.

Currently the largest unimplemented work, in order:
1. **Part LI §332 — P0.S1 (anti-spoof on every face match)** — next item in the locked sequence.
2. **Part LI §333-§334 — P0 security + robustness backlog (S1-S11, R1-R11)** — multi-month effort.
3. **Part LI §336 — P1.A pipeline.py decomposition into ~30 modules** — biggest architectural project queued.
4. **Part XXXV — Multi-layer classifier architecture** — six-layer plan, ships after P1.A.

The system is the sum of its decisions. Documenting the decisions is how we keep the system coherent across sessions, across contributors, and across time. The Part L named disciplines are how we ensure the decisions accumulate into doctrine rather than dissolving back into ad-hoc patterns.
