# P0.B2 Plan v2 — Q1 lock + closure-narrative template + closure-actual projection

**Plan v1 base:** `tests/p0_b2_faiss_async_rebuild_plan_v1.md` (auditor APPROVED 2026-05-21 with Q1 disposition Test 3 IN + Plan v2 recommended for closure-template lock + 5-surface landing checklist + Plan v2 §6 honest-count commitment template).

**Plan v2 absorbs:**
- **Q1 LOCK:** Test 3 (`test_add_embedding_during_async_rebuild_tracks_row_id`) **IN** — depth coverage of pending-add row_id tracking concurrency surface.
- **Closure-narrative paste-template** for each of 5 surfaces (prevents Convention-drift pattern that hit P0.S6+P0.S7+P0.B1 closures).
- **Closure-actual projection per Plan v2 §6 honest-count commitment template** (P0.B1 precedent — explicit 3-outcome enumeration with doctrine implications).

All Plan v1 D1-D5 contracts + §2 ORDERING INVARIANT + §3 crash-injection test scenarios + §4 Bug 2 comment correction stand UNCHANGED.

---

## §1. Q1 LOCK — Test 3 IN

**Decision:** include Test 3 (`test_add_embedding_during_async_rebuild_tracks_row_id`).

**Rationale (per auditor adjudication):**
- D2 mechanism refinement (pending-add row_id capture via `cursor.lastrowid`) is novel mechanism. Tests 1+2 cover happy-path + crash-recovery but neither directly tests the concurrency race: `add_embedding` racing with `rebuild_faiss_async`.
- Test 3 is depth coverage at the specific race surface.
- Defense-in-depth: structurally test the novel concurrency mechanism, don't rely solely on integration coverage.

**Locked anchor count: 10** (per Plan v1 §8.1 with Test 3 included). Q5 reading: `(10-11)/11 = −9.1%` → **ON-TARGET**.

**Surface:** Test 3 lands in `tests/test_faiss_async_rebuild.py` (fast-tier — uses mocks per Plan v1 §3.3 scenario).

---

## §2. Closure-narrative paste-template (5 surfaces)

Pre-drafted at Plan v2 to prevent Convention-drift pattern that hit P0.S6+P0.S7+P0.B1 closures. Each segment is verbatim-ready at closure with explicit count-substitution instructions.

### §2.1 — CLAUDE.md header (suite count + P0.B2 closure narrative + doctrine track-record update)

**Suite count line update:**
```
2608 → 2608 + N at P0.B2 closure
```
Where N = number of NEW collected tests at the test file level. Architect estimate N = 10-13 collected (10 logical anchors + 0-3 parametrize fan-out cases on Test 1's "for each known person" loop).

**P0.B2 closure narrative (prepend):** ~2-3 paragraph summary citing all 5 D-decisions + the falsification-watch outcome + ORDERING INVARIANT anchor + sentinel discipline + new informal observation banks.

**Doctrine track-record update — `### Phase-0-granular-decomposition-enables-accurate-estimates`:**
- Header line: increment supporting count based on closure-actual reading per §3 projection below.
- Add P0.B2 row to "Supporting (decomposed → ON-TARGET):" section ONLY IF closure lands ON-TARGET (within ±15% of mid 11, i.e. 9-13 anchors).

### §2.2 — Parent `complete-plan.md` P0.B2 status flip

**Locate:** the new "P0.B — Board-bug remediation track" section under parent complete-plan.md (created at P0.B1 closure).

**Add P0.B2 entry:**
```markdown
### P0.B2 — FAISS Async Rebuild Correctness (Bug 1 + Bug 2)

**Status:** `[CLOSED]` (closed YYYY-MM-DD)

**Closure note:** Closed via 5 D-decisions (D1 _fetch_all_embeddings_for_index 3-tuple + D2 _build_faiss_from_snapshot signature + D3 Phase 3 row_id capture + DB UPDATE batch + D4 sentinel discipline on async path + D5 crash-injection tests + Bug 2 comment correction). Sync `_rebuild_faiss` discipline now extended to async path. 10 logical anchors / N collected. Q5 closure +X% vs MID-RANGE 11 → [ON-TARGET / SLIGHT-DRIFT-UP / SLIGHT-DRIFT-DOWN / FALSIFICATION-TRIGGER]. Doctrine `### Phase-0-granular-decomposition-enables-accurate-estimates` [bumps 8 → 9 supporting / HOLDS at 8 / demotes 8 → 7]. Full closure narrative + ORDERING INVARIANT anchors + crash-safety table + 5 known limitations live at `c:\Users\jagan\dog-ai\dog-ai\complete-plan.md::P0.B2` + `c:\Users\jagan\dog-ai\dog-ai\CLAUDE.md` header.
```

### §2.3 — Subdir `complete-plan.md` P0.B2 closure narrative

**Locate:** prepend before P0.B1 closure narrative in subdir `complete-plan.md`.

**Section header:** `## P0.B2 — FAISS Async Rebuild Correctness (D1+D2+D3+D4+D5 + 10 anchors + sentinel discipline)  [CLOSED YYYY-MM-DD]`

**Full closure narrative includes:**
- Sub-PR sequence: Phase 0 audit → Plan v1 → Plan v2 → Phase 1-5 implementation
- Twin-filename pitfall 7th successful prevention confirmation
- Phase 0 premise ON-TARGET with 1 mechanism refinement (pending-add row_id)
- D1-D5 contract recap
- ORDERING INVARIANT comment block anchor at `core/db.py:~XXX`
- Crash-safety table (5 rows: 4 crash points + happy path)
- Q5 closure reading (concrete % calculated from closure-actual)
- Sub-rule + doctrine count updates per §3 projection
- Known limitations subsection (~5 items expected from impl-time discovery)

**Discipline counts at closure section** — use LOCKED +1-per-artifact convention (P0.S6 closure adjudication) with **explicit baseline citation**:

```markdown
**Discipline counts at closure**:

- **spec-first review cycle**: 43 → **44-for-44 at closure** (Phase 0 + Plan v1 + Plan v2 + closure = 4 artifacts × +1 each per locked +1-per-artifact convention; baseline 43 verified from P0.B2 Plan v1 close per Grep-baseline-before-drafting discipline).
- **`### Phase-0-granular-decomposition-enables-accurate-estimates` doctrine**: 8 → **[N] supporting instances** ([bump rationale per closure-actual]).
- **Strict-industry-standard mode**: 33 → **34 consecutive applications + 10 successful closures** (Phase 0 + v1 + v2 + closure = 4 artifacts × +1 each per locked convention).
- **Auditor-Q5**: 13 → **14 banked closures** at [N]% [READING_LABEL].
- **`### Twin-filename-pitfall-prevention`**: stays at 7 instances + operational rule 4 (no new prevention event at this closure).
- **Spec-time grep-verification**: 13 → **14 instances** (Pass-2 grep enumeration at Plan v1 §1).
- **Cross-cycle-handoff transparency precedent**: 8 → **9 successful** (Plan v1 Q5 framing-error self-correction + Plan v2 closure-template formalization).
- **Discipline-count-bump-needs-explicit-justification**: 10 → **[N] preventive** (closure narrative count-bump justifications).
- **Convention-drift-on-discipline-counts**: stays at 3 ([closure narrative used paste-template; clean]).
- **Grep-baseline-before-drafting**: 2 → **3 instances** (P0.B2 closure narrative drafted from grep-verified baseline per template).
- **Explicit-closure-honest-count-commitment**: 2 → **[3 or 4] instances** (Plan v2 §3 commitment MADE + closure HONORED OR DEMOTED).
- **Deferred-canary**: 9 → **10th application**.
```

### §2.4 — `to_be_checked.md` coverage matrix + P0.B2 verbatim entry

**Coverage matrix row:**
```markdown
| P0.B2 | _pending_ | _pending_ | _pending_ | _pending_ |
```

**Verbatim entry:**
```markdown
## P0.B2 — FAISS Async Rebuild Correctness (closed YYYY-MM-DD)

Surfaces shipped:
- core/db.py:932-944 — `_fetch_all_embeddings_for_index()` 3-tuple return with row_ids
- core/db.py:946-955 — `_build_faiss_from_snapshot()` accepts + returns idx_updates
- core/db.py:957-1008 — `rebuild_faiss_async` Phase 3 captures row_ids + DB UPDATE batch + sentinel discipline (ORDERING INVARIANT)
- core/db.py:702-712 — `add_embedding` captures `cursor.lastrowid` for pending-add tracking
- tests/test_faiss_sql_atomicity.py — 2 new slow-tier tests (prune→restart→recognize + crash mid-DB-UPDATE)
- tests/test_faiss_async_rebuild.py — 1 new test (concurrent add_embedding row_id tracking)
- tests/test_faiss_atomicity_invariants.py:29-32 — comment correction per Plan v1 §4

PASS signals (canary log should show):
- Pipeline startup: no AssertionError on sentinel check
- After dream-loop prune + process restart: every enrolled person recognized correctly
- `recognize()` returns correct identity for all 5+ household members post-restart
- No "FAISS dirty sentinel found — rebuilding to reconcile" message on normal boot
- "FAISS dirty sentinel found" appears IF and ONLY IF async rebuild was interrupted (crash recovery)

FAIL signals:
- Post-restart recognition returns (None, None, score) for known persons → DB faiss_idx update missing
- Sentinel always set on boot → async rebuild path never clears properly
- Sentinel never set during async rebuild → ORDERING INVARIANT violated

Test scenario:
1. Factory reset; enroll 5+ persons
2. Run a few conversation turns (some persons aging into stranger-prune eligible)
3. Wait for dream loop tick (or trigger prune manually)
4. Cleanly restart pipeline process
5. Verify each known person is recognized correctly on next greeting
6. Inject async-rebuild crash mid-DB-UPDATE (test only; not live canary) → verify sentinel triggers rebuild on next boot

Dependencies on other specs:
- P0.5 (CLOSED): FAISS+SQL atomicity sync pattern that P0.B2 extends to async path
- P0.B1 (CLOSED): same Board-bug remediation track
- P0.0.7 (CLOSED): event log foundation (no new event types in P0.B2)

Known limitations:
1. [populated at impl time from §X]
2. ...
```

### §2.5 — Memory files (3 updates)

**`feedback_auditor_q5_estimates_trail_grep.md`:**
- Add P0.B2 row to trajectory table with closure-actual reading
- Update banked-closures count: 13 → 14
- Trajectory line: `... → P0.B1 0% ON-TARGET → P0.B2 [N]% [LABEL]`

**`feedback_strict_industry_standard_mode.md`:**
- Add entry 14: `P0.B2 Phase 0 audit + Plan v1 + Plan v2 + Phase 1-5 closure (YYYY-MM-DD) — 33rd-34th consecutive applications + 10th successful closure`
- Cumulative count: 33 → 34 consecutive + 10 closures

**`feedback_grep_baseline_before_drafting.md`** (NEW file, if not yet created; otherwise update):
- 2 instances → 3 instances at P0.B2 closure

---

## §3. Closure-actual projection per Plan v2 §6 honest-count commitment template

**Per P0.B1 Plan v2 §6 precedent + auditor's standing recommendation at P0.B1 closure + Plan v1 Q5 reading verified at −9.1% ON-TARGET projection:**

| Closure-actual anchor count | Q5 reading vs mid 11 | Disposition | Doctrine effect (`### Phase-0-granular-decomposition`) |
|---|---|---|---|
| 9 anchors | `(9-11)/11 = −18.2%` | **SLIGHT-DRIFT-DOWN** | HOLDS at 8 supporting (no bump, no demote) |
| **10 anchors (Plan v2 LOCK)** | `(10-11)/11 = −9.1%` | **ON-TARGET** | **BUMPS 8 → 9 supporting** |
| 11 anchors | `(11-11)/11 = 0%` | **ON-TARGET** (exact mid) | BUMPS 8 → 9 supporting |
| 12 anchors | `(12-11)/11 = +9.1%` | **ON-TARGET** | BUMPS 8 → 9 supporting |
| 13 anchors | `(13-11)/11 = +18.2%` | **SLIGHT-DRIFT-UP** | HOLDS at 8 supporting |
| ≤8 anchors | `≤−27.3%` | approaching falsification | edge case — within ±30% → still HOLDS at 8 |
| ≥14 anchors | `≥+27.3%` | approaching falsification | edge case — within ±30% → still HOLDS at 8 |
| ≤7 anchors | `≤−36.4%` | **FALSIFICATION TRIGGER** | **DEMOTES 8 → 7 supporting** |
| ≥15 anchors | `≥+36.4%` | **FALSIFICATION TRIGGER** | **DEMOTES 8 → 7 supporting** |

**Falsification-watch active at P0.B2 closure** (per auditor banking — 2nd post-elevation cycle). Mid-band tolerance is generous (anything 9-13 is ON-TARGET → bumps). Demotion only if closure lands at ≤7 or ≥15 anchors.

**Architect commitment locked at Plan v2 §3:**

> Doctrine demotion will fire if closure lands at ≤7 or ≥15 anchors. Doctrine bumps to 9 supporting if closure lands in [9, 13]. Architect commits to honest count at closure — no silent over-bumping to avoid demotion, no silent under-counting to avoid SLIGHT-DRIFT label. **Closure-actual count is the binding number for doctrine disposition.**

This is the **2nd instance of Explicit-closure-honest-count-commitment** discipline applied (1st was P0.B1 Plan v2 §6, honored at P0.B1 closure with doctrine bump 7 → 8).

---

## §4. Minor refinements from Plan v1 re-read

### §4.1 — `cursor.lastrowid` capture site clarity

Plan v1 §5 D3 said "captures `cursor.lastrowid` immediately after INSERT" but didn't specify the variable handoff between `with self.transaction():` block (where INSERT happens) and the subsequent `_pending_adds_during_rebuild.append(...)` call (line 707).

**Refinement:** the INSERT cursor is the connection-default cursor (`self._conn.execute(...)` returns a cursor with `lastrowid` accessible). Capture immediately after INSERT, inside the transaction block:

```python
with self._index_lock:
    faiss_idx = self.index.ntotal
    with self.transaction():
        cur = self._conn.execute(
            "INSERT INTO embeddings (...) VALUES (...)",
            (...)
        )
        _row_id = cur.lastrowid          # ← capture inside transaction
    try:
        self.index.add(emb)
        self._idx_to_person[faiss_idx] = person_id
        if self._rebuild_in_progress:
            self._pending_adds_during_rebuild.append((emb[0].copy(), person_id, _row_id))   # ← use captured row_id
        self._save_faiss()
    except Exception as e:
        ...
```

This avoids the implicit-cursor pattern (calling `.execute()` on `self._conn` without storing the returned cursor object). Plan v2 locks the explicit-cursor variant.

### §4.2 — Test 3 fixture isolation

Test 3 (`test_add_embedding_during_async_rebuild_tracks_row_id`) runs in fast-tier `tests/test_faiss_async_rebuild.py`. The file's existing tests use a `db` fixture that monkeypatches the executor. Test 3 needs the same fixture pattern but with concurrent `add_embedding` interleaving.

**Lock at Plan v2:** Test 3 uses the existing `db` fixture + leverages `asyncio.Event` to coordinate the "pause rebuild after Phase 1, run add_embedding, resume rebuild" sequence. No new fixture needed.

---

## §5. Quality gate checklist (unchanged from Plan v1; 10 APPLIES + 1 N/A privacy)

No structural changes from Plan v1. Closure-template formalization at §2 is documentation work, not new architecture.

---

## §6. Discipline counts at Plan v2 close

- **Spec-first review cycle:** 43 → **44 at Plan v2 close** per locked +1-per-artifact convention.
- **Strict-industry-standard mode:** 33 → **34 consecutive applications** + 9 closures (in-flight to 10 at P0.B2 close).
- **`### Phase-0-catches-wrong-premise`:** STAYS at 7.
- **`### Phase-0-granular-decomposition-enables-accurate-estimates`:** STAYS at 8 supporting (FALSIFICATION-WATCH ACTIVE; closure outcome per §3 projection determines disposition).
- **`### Twin-filename-pitfall-prevention`:** STAYS at 7 instances + 4 operational rules.
- **Auditor-Q5:** 13 banked + 1 in-flight at −9.1% vs mid 11 (ON-TARGET projection).
- **Cross-cycle-handoff transparency precedent:** STAYS at 8 (P0.B2 Plan v1 framing correction was the 8th; Plan v2 has no new in-flight item).
- **Grep-baseline-before-drafting:** STAYS at 2 instances (P0.B1 closure → P0.B2 Phase 0 application + Plan v1 continuation; P0.B2 closure narrative drafting will be 3rd instance).
- **Explicit-closure-honest-count-commitment:** STAYS at 2 instances (P0.B1 commitment + honoring); Plan v2 §3 above IS the 3rd-instance commitment-MADE event for P0.B2 — banked at closure if honored.
- **Discipline-count-bump-needs-explicit-justification:** STAYS at 10 preventive.
- **Convention-drift-on-discipline-counts:** STAYS at 3 instances (closure-narrative paste-template at §2 should prevent recurrence).
- **Deferred-canary:** STAYS at 9th application in-flight.
- **Spec-time grep-verification:** STAYS at 13.

---

## §7. Open questions for auditor (0)

No new open questions at Plan v2. Q1 from Plan v1 locked per auditor adjudication.

**Architect prediction:** APPROVED 0 items → ship to developer per HEAVY-band v1 → v2 → developer cadence. Developer contract: ~6-10 hours (5-surface refactor + 3 new tests + closure narrative drafting via paste-template).

---

## §8. Implementation handoff readiness check (architect self-audit)

- ✅ All 5 D-decisions named with surfaces + contracts (Plan v1 §5).
- ✅ Q1/Q2/Q3 dispositions locked + Q1 Test 3 INCLUDED per auditor verdict.
- ✅ ORDERING INVARIANT comment block + 10-step verbatim template + crash-safety table (Plan v1 §2).
- ✅ Pass-2 grep enumeration locked (Plan v1 §1).
- ✅ D5 crash-injection test scenarios specified (Plan v1 §3; Test 3 LOCKED IN).
- ✅ Bug 2 comment correction text locked (Plan v1 §4).
- ✅ Closure-narrative paste-template for 5 surfaces (Plan v2 §2).
- ✅ Closure-actual projection per honest-count commitment template (Plan v2 §3).
- ✅ Minor refinements (cursor.lastrowid capture site + Test 3 fixture isolation) (Plan v2 §4).
- ✅ 11-gate checklist verified (Plan v1 §7).
- ✅ Cross-spec impact analysis (Plan v1 §9 / Phase 0 §7).
- ✅ Pre-mortem 12 modes (Phase 0 §5).

**Developer contract estimate:**
- **Phase 1** (~1h): D1+D2 helper signature changes + Pass-2 grep verification + update direct callers in `tests/test_faiss_async_rebuild.py` if any.
- **Phase 2** (~2-3h): D3 `add_embedding` cursor.lastrowid capture + `_pending_adds_during_rebuild` 3-tuple extension + Phase 3 swap logic + DB UPDATE batch.
- **Phase 3** (~1h): D4 `_mark_faiss_dirty` + `_clear_faiss_dirty` calls in `rebuild_faiss_async` per ORDERING INVARIANT.
- **Phase 4** (~2-3h): D5 — 3 new tests (Test 1 + Test 2 in slow-tier + Test 3 in fast-tier) + Bug 2 comment correction.
- **Phase 5** (~1h): full-suite verification + 5-surface closure landing via §2 paste-template + memory bankings.

**Total: ~7-10 hours.** Falls within Phase 0 estimate of 6-10 hours.

---

**End of Plan v2.** Ready to forward to auditor.

**Architect prediction:** APPROVED 0 items → ship to developer.
