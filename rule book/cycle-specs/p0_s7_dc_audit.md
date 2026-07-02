# P0.S7.D-C — Delete `_build_cross_person_excerpts` legacy block — Phase 0 Audit

**Date:** 2026-05-19
**Author:** architect
**Status:** Phase 0 — grep-verified findings, zero production-code changes. Standing by for auditor review before D-decision lock and Plan v1.

**Companion document trail (forthcoming):**
- `tests/p0_s7_dc_plan_v1.md` — after Phase 0 sign-off + D-decision lock
- `tests/p0_s7_dc_plan_v2.md` — after Plan v1 review

---

## 1. Premise (P0.S7 Phase 0 audit framing recall)

P0.S7's Phase 0 audit (`tests/p0_s7_audit.md`) decomposed "Phase 3B" into 5 deferred items: D-A through D-E. D-A shipped 2026-05-18 as P0.S7 (with P0.S7.1 observability follow-up). D-C is the **legacy block cleanup** — delete `_build_cross_person_excerpts` (pipeline.py:1202) since `<<<SHARED CONTEXT>>>` (P0.S7 D-A) + `<<<ROOM>>>` (S113 P3B.1) together cover what it produced.

P0.S7 Plan v2 §1 D6 + §11 explicitly framed D-C as **canary-gated**: ship D-C ONLY after a live multi-person canary confirms the new blocks cover the use case. The user's 2026-05-19 direction reverses that gate (see §3 quality-flag below).

---

## 2. Sub-pattern A premise-check (architect's pre-Phase-0 mental model vs grep-verified state)

**Pre-Phase-0 assumed premise:** "D-C is a clean deletion — just remove `_build_cross_person_excerpts` function + its one call site + tests that exercise it. ~quarter-day cleanup."

**Grep-verified actual state (2026-05-19):**

`_build_cross_person_excerpts` is referenced at **10 surfaces** across the codebase. The function-level deletion is one of them; the others form a dependency surface that has to be reasoned about:

| Site | Type | Disposition |
|---|---|---|
| `pipeline.py:1202-1290` | Function definition (89 LOC) | DELETE |
| `pipeline.py:5419` | Call site in `conversation_turn` (assigns `room_context` local) | DELETE |
| `pipeline.py:5423` | `[Brain] Context: ... room=yes/no` summary log field — references `room_context` local | **DECISION NEEDED (D2 below)** |
| `pipeline.py:5448-5449` | `room_context` prepended to `prompt_addendum` | DELETE |
| `pipeline.py:1326` | Comment reference in `_build_shared_context_block` docstring | UPDATE (comment-only, not code) |
| `test_pipeline.py` | Test references (count TBD — Plan v1 grep-enumerates) | DELETE / REPOINT |
| `KARAOS_KNOWLEDGE.md` | Doc reference | UPDATE (separate from per-PR; bi-weekly refresh) |
| `tests/p0_s7_audit.md` | Audit reference (historical) | LEAVE (historical record) |
| `tests/p0_s7_plan_v1.md` | Plan reference (historical) | LEAVE (historical record) |
| `tests/p0_s7_plan_v2.md` | Plan reference (historical) | LEAVE (historical record) |
| `tests/p0_s7_1_spec.md` | Spec reference (historical) | LEAVE (historical record) |

**Premise re-set:** D-C is NOT a simple 3-site deletion. It's a 4-decision surface — the `room=yes/no` summary field semantics need a deliberate disposition, plus disputed-session label coverage needs verification against `<<<ROOM>>>` Section 1.

This may or may not be a sub-pattern A 5th instance — depends on the auditor's strict-read. Architect's lean: borderline. The premise was off but not dramatically (it's a "cleanup is slightly less clean than expected" finding, not a "the actual gap is somewhere else entirely" finding). Auditor adjudicates at closure.

---

## 3. Pre-decision flags (architect raises BEFORE drafting plan)

### 3.1 Canary-gate override (QUALITY FLAG — needs auditor sign-off)

P0.S7 Plan v2 §11 + the Phase 0 audit framed D-C as **canary-gated**. The user's 2026-05-19 direction:

> "lets move to D-C ... D-B ... D-D ... D-E ... and we have to include the γ bullet behavioral-target strengthening ... i will do the live sessions once all these are implemented"

This reverses the gate — D-C ships BEFORE the multi-person canary that was supposed to validate D-A first.

**Quality risk:** if SHARED CONTEXT block has a subtle gap that the legacy block was masking, deleting the legacy block surfaces the gap only AFTER all 4 architectural items + γ strengthening are shipped. Debugging would be harder (more variables changed simultaneously).

**Quality mitigation (architect's lean):** ship D-C as a **two-stage deletion**:
- **Stage 1**: flag-gate the legacy block behind `CROSS_PERSON_EXCERPTS_ENABLED: bool = False` (default OFF) so rollback is one-flag-flip. Function code stays in source for the duration of D-B/D-D/D-E work. Both blocks coexist code-wise but only `<<<SHARED CONTEXT>>>` + `<<<ROOM>>>` render at runtime.
- **Stage 2**: HARD DELETE the function + tests after the user's eventual canary validates the bundled work (per their stated plan).

Stage 1 is the D-C scope. Stage 2 is a follow-up after the user's canary. This preserves the canary-gate semantic while not blocking the user's queue.

**Auditor verdict requested**: lock the two-stage approach OR push for single-stage hard-delete in D-C OR demand canary BEFORE D-C ships?

### 3.2 γ strengthening — separate sub-PR (P0.S7.4) recommended

The user's 2026-05-19 direction also says:

> "we have to include the γ bullet behavioral-target strengthening (call search_memory autonomously on first mention)"

This is a **prompt-engineering change** unrelated to D-C/D-B/D-D/D-E's structural work. Mixing it into any of these specs would muddy the closure narrative (prompt iteration discipline ≠ architectural-cleanup discipline; different review surfaces).

**Architect's recommendation:** P0.S7.4 — γ strengthening as its own micro-PR. Same shape as P0.S7.3 (KAIROS fix) — direct-to-developer spec, ~30 min, no Phase 0 audit needed because it's not architectural. Can ship in parallel with D-C/D-B/D-D/D-E.

**Auditor verdict requested:** lock P0.S7.4 as standalone, OR bundle into one of the bigger items, OR something else?

---

## 4. What `_build_cross_person_excerpts` actually produces

Grep-verified from `pipeline.py:1202-1290`. The function emits a 3-section block when `len(active_sessions) >= 2`:

### Section A — Active speakers with role labels

```
Jagan (best friend — speaking now), Lexi (visitor), Priya (known person)
```

Roles: `best friend` / `visitor` (stranger) / `known person` / **`disputed identity`** (S91 dispute discipline). The disputed-identity label is load-bearing — comes from the `_is_disputed(pid)` check at line 1234.

### Section B — Cross-person excerpts (recent turns from OTHER speakers)

```
Lexi (2m ago): "I've been feeling anxious about my thesis"
you [to Lexi] (1m ago): "What's the deadline?"
Lexi (just now): "Friday at noon"
```

Per-line format: `{speaker_name OR "you [to X]"} ({age_label}): "{content[:120]}"`. Filtered by `_cx_snap2.started_at` (session-boundary filter — S111 Critical #2). Last 6 messages per other-person.

### Section C — (nothing — block ends after excerpts)

Returns full block string OR `None` if `len(active_sessions) <= 1`.

---

## 5. Coverage analysis — does `<<<SHARED CONTEXT>>>` + `<<<ROOM>>>` produce what we're deleting?

| Legacy block feature | `<<<ROOM>>>` (S113 P3B.1) | `<<<SHARED CONTEXT>>>` (P0.S7 D-A) | Coverage |
|---|---|---|---|
| Active speakers + roles (best_friend / visitor / known) | ✓ Section 1 | ✗ | ✓ via ROOM |
| **`disputed identity` role label (S91)** | **NEEDS VERIFICATION** | ✗ | **POTENTIAL GAP — D-decision needed** |
| Cross-person excerpts (other speakers' recent turns) | ✓ Section 3 (interleaved) | ✓ (persistent-DB scoped) | ✓ both |
| `you [to X]` addressee label | ✓ Section 3 | ✓ (P0.S7 P2 + addressed_to=None graceful fallback) | ✓ both |
| Age suffix ("just now" / "Xm ago") | ✓ Section 3 | ✓ | ✓ both |
| Session-boundary filter (`started_at`) | ✓ implicit (in-memory history) | ✓ via `room_session_id` scoping | ✓ both via different mechanisms |
| Single-source-of-truth in-memory? | ✓ `_conversation_store._history` | ✗ (persistent DB) | ✓ for fresh turns |

**Gap surfaced: disputed-identity role label** — the legacy block at line 1234 explicitly emits "disputed identity" as a role. Does `<<<ROOM>>>` Section 1 do the same? Plan v1 grep-verifies this. If gap exists, Plan v1 either (a) extends `<<<ROOM>>>` Section 1 to emit the label OR (b) adds a `<<<IDENTITY DISPUTED>>>` block coverage check OR (c) banks the gap as a future micro-PR if non-load-bearing.

---

## 6. D-decisions surfaced

| ID | Topic | Architect's lean |
|---|---|---|
| D1 | Deletion strategy | **(a) Two-stage**: Stage 1 (this D-C) flag-gates legacy block behind `CROSS_PERSON_EXCERPTS_ENABLED=False`; Stage 2 (post-canary follow-up) hard-deletes. Preserves canary-gate semantic AND unblocks the user's bundled queue. |
| D2 | `[Brain] Context: ... room=yes/no` summary field disposition | **(a) Repoint to `<<<ROOM>>>` block render**: the summary field's semantic intent was "multi-person context is in scope this turn"; new ROOM block is the right source. Change `room_context` local to read from the ROOM block's render path (or boolean `len(active_sessions) >= 2`). Backward-compat for grep tooling. |
| D3 | Disputed-identity role label gap | **NEEDS GREP VERIFICATION in Plan v1**: if `<<<ROOM>>>` Section 1 emits the label, no action. If gap exists, extend Section 1 (one-line change, low risk). |
| D4 | Test surface impact | Plan v1 grep-enumerates all test sites referencing `_build_cross_person_excerpts`. Each test either (a) gets DELETED if it directly tests the legacy function's render OR (b) gets REPOINTED to the new `<<<ROOM>>>` / `<<<SHARED CONTEXT>>>` block tests. |
| D5 | `room_context` prepending into `prompt_addendum` (pipeline.py:5448-5449) | DELETE under D1.a flag — `<<<ROOM>>>` and `<<<SHARED CONTEXT>>>` are injected directly in `_build_system_prompt`; the legacy `prompt_addendum` injection path is redundant when the new blocks render. |
| D6 | Token-budget impact | Net reduction. Validation-window overlap (~+300 tokens documented in P0.S7 Plan v2 §11) eliminates when Stage 1 disables the legacy block. ROOM + SHARED CONTEXT alone is ~300 tokens less per multi-person turn. |
| D7 | Structural invariant for "no legacy block prefix on prompt_addendum" | NEW Phase 3 AST test: scan `conversation_turn` body asserting `_build_cross_person_excerpts` is NOT called when `CROSS_PERSON_EXCERPTS_ENABLED=False`. Inverse-check pattern (any prepending of multi-person blocks to `prompt_addendum` is forbidden when flag is off). |
| D8 | Phase decomposition + test count | ~4-6 tests total. Suite delta forecast: 2367 → ~2371. Effort: ~half-day (no Phase 2 LLM-extraction work needed). |

---

## 7. Test surface impact

Plan v1 grep-enumerates `_build_cross_person_excerpts` test references. Initial scope estimate:

- `test_pipeline.py` carries some legacy tests directly asserting the block's render shape (e.g., Session 111 Critical #2/#3 tests, S91 Finding M disputed-identity test). Count TBD.
- Each test gets a disposition: DELETE (if function deletion makes it unreachable) OR REPOINT (if it can be re-targeted to `<<<ROOM>>>` Section 1 / `<<<SHARED CONTEXT>>>` render).

**Architect's lean (DEFERRED to Plan v1 grep):** if test count is small (~5 or fewer), DELETE all and rely on `<<<ROOM>>>` + `<<<SHARED CONTEXT>>>` existing test coverage. If test count is larger (>10), repoint critical tests (especially disputed-identity / session-boundary) to the new blocks.

---

## 8. Effort estimate + phase shape

D-C scope under D1.a (two-stage flag-gate):

| Phase | Scope | Tests | Time |
|---|---|---|---|
| 1 | `CROSS_PERSON_EXCERPTS_ENABLED` config flag + flag-gated call site at pipeline.py:5419 | +2 | ~quarter-day |
| 2 | Repoint `[Brain] Context:` room=yes/no field (D2) + disputed-identity role label coverage if gap (D3) | +1-2 | ~quarter-day |
| 3 | Structural invariant (D7 AST scan) + test repointing/deletion (D4) | +1-2 | ~quarter-day |
| 4 | Deliberate-regression confirmations + closure | +0 | ~quarter-day |

**Total: ~4-6 tests, ~half-day, suite 2367 → ~2371-2373.**

D-C Stage 2 (hard-delete after eventual canary) is a separate follow-up — quick removal of the function definition + flag once canary validates the bundled D-C+D-B+D-D+D-E+γ work.

---

## 9. Discipline-count predictions

- **Spec-first review cycle**: 10-for-10 → **11-for-11** on closure (D-C added).
- **Sub-pattern A**: stays at 4 instances OR bumps to 5 instances (borderline — depends on auditor's strict-read of whether "D-C is more complex than expected" qualifies as wrong-premise). Architect's lean: BORDERLINE. If the 10-surface dependency-fan-out + the room=yes/no semantic flip + the disputed-identity gap-verification are read as "the simple deletion premise was off," counts as 5th instance. If read as "routine implementation finding," stays at 4. **5th instance would cross the threshold (5+) for sub-pattern A elevation to standalone `###` doctrine in CLAUDE.md.** Worth explicit auditor adjudication.
- **Tripwires-must-match-deferral-surface**: stays 4-for-4 unless D7's "no legacy prefix on prompt_addendum" AST scan counts as a deferral tripwire. Architect's lean: it's forward-property structural (matches P0.S6 D3 invariants), not deferral-guarding. Stays 4-for-4.
- **Developer-improves-on-spec**: stays 6-for-6 unless code phase surfaces a mechanism improvement.
- **Induction-surfaces-invariant-gaps**: stays 7-for-7.
- **Canary-finding tracker**: stays at 2 instances (no new canary-finding banked by this audit).
- **Canary-gate override**: this is a NEW discipline observation — "spec explicitly reverses its own canary-gate per user direction." Worth banking the rationale (D1.a two-stage approach preserves the canary semantic via flag-gating). Not yet a numbered discipline.

---

## 10. Threats / risks

1. **Disputed-identity role label gap (D3)** — if `<<<ROOM>>>` Section 1 doesn't carry the label, flag-gating the legacy block means brain loses the "disputed identity" cue in multi-person scenes. Mitigation: Plan v1 grep-verifies; Plan v1 extends ROOM Section 1 if gap exists.

2. **`[Brain] Context: ... room=yes/no` semantic flip (D2)** — any tool / log-grep relying on the field's current semantic (legacy block produced output) will need to be aware that post-D-C, the field means "ROOM block would have rendered." Low-impact because: (a) no production code reads the log line; (b) it's a developer observability surface only.

3. **D1.a stage-1 dead code** — flag-gated legacy block stays in pipeline.py source even though it never executes. Architect's defense: ~89 LOC dead code under explicit `if not CROSS_PERSON_EXCERPTS_ENABLED:` short-circuit is preferable to hard-delete-before-canary. Stage 2 cleans up post-canary.

4. **Canary-gate override (§3.1)** — reverses P0.S7 Plan v2 §11 explicit canary-gate. Quality-mitigated by D1.a two-stage approach (flag-gating preserves rollback path). Worth explicit auditor sign-off.

5. **Test surface unknown until Plan v1 grep (D4)** — if test count is large, repointing becomes a meaningful chunk of effort.

---

## 11. Next steps

1. **Auditor reviews this Phase 0 audit.** Specifically: (a) D1 — two-stage approach OK or push for single-stage? (b) D2 — repoint summary field disposition? (c) D3 — gap-verification approach? (d) §3.1 canary-gate override — explicit sign-off? (e) §3.2 γ strengthening — standalone P0.S7.4? (f) §2 borderline sub-pattern A 5th instance — strict-read adjudication?
2. **D-decisions locked** at Phase 0 sign-off.
3. **Plan v1** drafted with locked D-decisions + Plan v1 grep-enumeration of test surface impact.
4. **Plan v1 review** by auditor.
5. **Plan v2** drafted incorporating precision items.
6. **Joint sign-off** → developer handoff for 4-phase implementation.

---

## 12. Reference documents

- `tests/p0_s7_audit.md` — Phase 0 audit of P0.S7 (D-A first-slice framing; D-C bookmark)
- `tests/p0_s7_plan_v2.md` — P0.S7 D-A Plan v2 (§11 canary-gate for D-C)
- `tests/p0_s7_1_spec.md` — P0.S7.1 observability micro-PR (banks SHARED CONTEXT log signal)
- `tests/p0_s7_2_plan_v2.md` — P0.S7.2 cross-session memory Plan v2 (Plan v2 §11.10 re-canary discipline)
- `tests/p0_s7_3_spec.md` — P0.S7.3 KAIROS sibling fix
- `pipeline.py:1202-1290` — `_build_cross_person_excerpts` function (deletion target)
- `pipeline.py:5419-5449` — call site + prompt_addendum prepending
- `pipeline.py:5423` — `[Brain] Context: ... room=yes/no` summary log line (D2 repoint target)
- `pipeline.py:1234` — disputed-identity role label site (D3 gap-verification anchor)
- S113 `<<<ROOM>>>` block + S91 disputed-session discipline — coverage comparison anchors

---

**Standing by for auditor verdict on §3 quality-flags + §6 D-decisions before drafting Plan v1.**
