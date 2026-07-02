# P0.R1 Plan v2 — ONNX session wrap (PI #1 absorption: §1.1 enumeration correction + §8 baseline-count clarification)

**Plan v1 base:** `tests/p0_r1_onnx_session_wrap_plan_v1.md` (auditor surfaced 1 PI at Plan v1 review 2026-05-23 — §1.1 Pass-2 grep undercount on pipeline.py call sites; OPTIONAL-Plan-v2 path BLOCKED at this surface; `### Zero-precision-items-at-auditor-review` stays at 9 instances per Plan v1 review surface NOT firing).

**Plan v2 scope (minimal correction per auditor lean Option (a)):**

- **§1** — PI #1 absorbed: §1.1 enumeration corrected from "3 pipeline.py sites" to **4 pipeline.py sites** + vision_channel.py:247 honest-banking note (6th caller, already None-safe per Session 48 wiring).
- **§1.4** — banking shape: `Plan-v1-Pass-2-grep-undercount` 4 → 5 instances (auditor-surfaced at Plan v1 review — 2nd consecutive cycle after P0.S9).
- **§8** — `### Phase-0-catches-wrong-premise` baseline clarification: +3 jump from 9 → 12 across P0.S10/P0.S11/P0.8 WONTFIX closures earlier today explicitly enumerated for grep-verifiable audit trail.
- **No D-decision changes** — D1 contract from Plan v1 §2 stays canonical.
- **No anchor count changes** — Plan v1 §3 LOCK at 4 anchors NARROW band [3.4, 4.6] mid 4 stays canonical.
- **No honest-count commitment changes** — Plan v1 §4 commitment (15th instance MADE) stays canonical; Plan v2 does NOT re-make.
- **1 informal observation bump** — `Plan-v1-Pass-2-grep-undercount` 4 → 5 instances.

---

## §1. PI #1 absorption — §1.1 enumeration correction + §8 baseline clarification

### §1.1 CORRECTED — Pass-2 grep enumeration of `embedder.embed()` call sites (6 total: 4 pipeline.py + 1 enroll.py + 1 vision_channel.py)

Auditor's Pass-2 grep verification surfaced 6 distinct `embedder.embed(face_crop)` / `face_embedder.embed(crop)` call sites across production code. Plan v1 §1.1 enumerated 5 (with 1 misclassified) and bundled the 2 enrollment-flow sites into "3 pipeline.py sites" framing. Corrected enumeration:

| # | File:line | Caller context | Downstream consumer | None-safe? |
|---|---|---|---|---|
| 1 | `enroll.py:80` | Standalone CLI enrollment | CLI returns/exits | NOT yet — D1 Phase 1 adds `if embedding is None: sys.exit(1)` |
| 2 | `pipeline.py:3356` | `first_boot_flow` enrollment | `pending_embeddings.append((embedding, _fb_verdict))` | NOT yet — D1 Phase 1 adds skip + log |
| 3 | `pipeline.py:3429` | `enrollment_flow` enrollment | `pending_embeddings.append((embedding, _en_verdict))` | NOT yet — D1 Phase 1 adds skip + log |
| 4 | `pipeline.py:6573` | `_background_vision_loop` | `temporal_buffer.add_and_pool(det.bbox, raw_embedding, track_id=...)` | NOT yet — D1 Phase 1 adds skip + log |
| 5 | `pipeline.py:6965` | Camera fallback path | `db.recognize(_emb, ...)` + `_maybe_record_silent_obs(_emb, ...)` | recognize() handles None per P0.5 degraded-mode; silent_obs may not — D1 Phase 1 adds guard before silent_obs call |
| 6 | `core/vision_channel.py:247` | Shadow channel (Session 48 wiring) | wrapped in try/except + explicit `if emb is None: continue` at line 251 | **ALREADY None-safe** — no edit needed |

**Misclassification corrected:** Plan v1 §1.1 listed `core/db.py::recognize()` and `core/db.py::add_embedding()` as "callers" of `embed()`. They are DOWNSTREAM CONSUMERS that receive the embedding as a parameter — not callers that invoke `embed()` themselves. The actual callers are at the 6 sites in the table above. recognize() + add_embedding() still need to handle None safely (verified per P0.5 closure narrative), but they are not the catching layer for the None-return contract.

### §1.2 D1 None-return safety mitigation (LOCKED at Plan v2)

After D1 changes `embed()` return type from `np.ndarray` to `np.ndarray | None`, the 5 caller-sites that currently assume np.ndarray return need explicit None handling:

**Plan v2 D1 implementation contract (replaces Plan v1 §1.1 "3 pipeline.py sites" framing):**

- **enroll.py:80** — D1 Phase 1: add `if embedding is None: print("[Enroll] ERROR: face embedding failed (CUDA+CPU cascade); aborting"); sys.exit(1)`.
- **pipeline.py:3356** (`first_boot_flow`) — D1 Phase 1: add `if embedding is None: continue` BEFORE the `pending_embeddings.append((embedding, _fb_verdict))` line. Log: `[Pipeline] first_boot_flow: face embedding failed, skipping this enrollment frame`.
- **pipeline.py:3429** (`enrollment_flow`) — D1 Phase 1: symmetric to 3356; add `if embedding is None: continue` BEFORE the `pending_embeddings.append((embedding, _en_verdict))` line. Log: `[Pipeline] enrollment_flow: face embedding failed, skipping this enrollment frame`.
- **pipeline.py:6573** (`_background_vision_loop`) — D1 Phase 1: add `if raw_embedding is None: continue` BEFORE `temporal_buffer.add_and_pool(...)`. Log: `[Pipeline] background scan: face embedding failed, skipping frame`.
- **pipeline.py:6965** (camera fallback) — D1 Phase 1: add `if _emb is None: continue` BEFORE both `db.recognize(_emb, ...)` and `_maybe_record_silent_obs(_emb, ...)` calls. Log: `[Pipeline] camera fallback: face embedding failed, skipping`.

**Out-of-scope per auditor banking:** `core/vision_channel.py:247` (6th caller) is already None-safe via existing Session 48 try/except + `if emb is None: continue` at line 251. Mention-only for completeness.

### §1.3 D1 scope unchanged

D1 production code scope from Plan v1 §2.1 unchanged: `core/vision.py::FaceEmbedder.embed()` body + `__init__()` instance attrs. ~10 LOC + 1 instance attribute. Smallest D1 scope in any post-P0.S8 cycle.

D1 caller-site mitigations (per §1.2 above) are Phase 1 implementation work, NOT separate D-decisions. They consume D1's None-return contract; they don't change D1's production code shape.

### §1.4 Banking shape — Plan-v1-Pass-2-grep-undercount 4 → 5 instances

This is the 5th instance of the discipline:

- **1st** — P0.B3 Plan v1 §1.1 missed `tests/test_kuzu_crash_injection.py` (test-file naming pattern)
- **2nd** — P0.B5 Plan v1 §1.3 missed `tests/test_faiss_sql_atomicity.py:193` monkeypatch site (test-monkeypatch API)
- **3rd** — P0.B6 Plan v1 §3.1 D1 anchor's own literal source contained forbidden marker pattern (test-source self-reference)
- **4th** — P0.S9 Plan v1 §1.1 missed 4 `repair_gallery` references (test_pipeline.py 2 sites + KARAOS_KNOWLEDGE.md doc + core/audit.py docstring); plus cross-spec allowlist line-shift surface at Phase 5
- **5th (NEW, this banking)** — P0.R1 Plan v1 §1.1 enumerated "3 pipeline.py sites" but reality is **4 pipeline.py sites** (missed enrollment-flow sites at 3356 + 3429); plus misclassified recognize() + add_embedding() as "callers" when they're downstream consumers; plus missed vision_channel.py:247 caller (already None-safe per Session 48). Auditor's Pass-2 grep verification at Plan v1 review surfaced the drift.

**2 consecutive cycles (P0.S9 + P0.R1) where auditor's Pass-2 grep verification surfaces Plan v1 §1.1 enumeration drift.** Pattern is consistent — per the locked operational-rule extension candidacy at P0.S9 closure (4-instance threshold reached). 5th instance reinforces the candidacy. If a 6th instance surfaces at the next cycle's Plan v1 review, the operational-rule extension should be formalized under `feedback_spec_time_grep_verification.md` (e.g., "Pass-2 grep enumeration MUST be auditor-verified via independent re-grep before Plan v1 approval").

**Architect-side meta-observation banked (architect-memory only):** Auditor Pass-2 verification at Plan v1 review is the LOAD-BEARING catching layer for Plan v1 quality — not duplicative discipline. The 2 consecutive blocked-by-PI cycles (P0.S9 arithmetic drift caught + P0.R1 enumeration drift caught) demonstrate the auditor cross-check fires PRECISELY where architect proactive Pass-2 falls short. New informal observation candidate: `feedback_zero_precision_items_pre_closure_predictions.md` — architect's pre-Plan-v1-review predictions of "APPROVED 0 items" blocked at Plan v1 review for 2 consecutive cycles. Watch threshold: 3+ consecutive blocked-by-PI cycles → operational rule "architect prediction of 0 items should be reframed as 'submitted for auditor cross-check; expecting PI surface'".

### §1.5 §8 baseline-count clarification — `### Phase-0-catches-wrong-premise` +3 jump from 9 → 12 across P0.S10/P0.S11/P0.8 WONTFIX closures (per auditor non-blocking flag)

The +3 jump from 9 → 12 across this baseline (post-P0.S9 closure 9 instances → pre-P0.R1 Phase 0 baseline 12 instances) is explicitly attributable to 3 same-day WONTFIX closures earlier today:

| Cycle | Closure event | Sub-pattern A instance | `### Phase-0-catches-wrong-premise` bump |
|---|---|---|---|
| **P0.S10** WONTFIX 2026-05-23 | parent `complete-plan.md::P0.S10` `[OPEN]` → `[CLOSED]` | 10th instance opposite-direction subspecies (terminal_output .gitignore protection already in place since 2026-05-02; structural test at P0.S6 N1 2026-05-21) | 9 → 10 |
| **P0.S11** WONTFIX 2026-05-23 | parent `complete-plan.md::P0.S11` `[OPEN][VERIFY]` → `[CLOSED]` | 11th instance opposite-direction subspecies (system_only reachability tests already in place at P0.S3 + P0.S4 + P0.S7) | 10 → 11 |
| **P0.8** WONTFIX 2026-05-23 | parent `complete-plan.md::P0.8` `[OPEN][VERIFY]` → `[CLOSED]` | 12th instance opposite-direction subspecies (per-tool timeout protection shipped at original P0.8 closure + P0.8.1 + P0.8.2 follow-ups) | 11 → 12 |

All 3 closure narratives in parent `complete-plan.md` explicitly enumerate the sub-pattern A bump per the `### Discipline-count-bump-needs-explicit-justification` discipline. Grep-verifiable trail at `c:\Users\jagan\dog-ai\complete-plan.md::P0.S10` + `P0.S11` + `P0.8` row Closure rationale paragraphs.

**Mechanism:** WONTFIX closures DO bump event-driven doctrines (like `### Phase-0-catches-wrong-premise`) when the Phase 0 audit IS the catching event, but DO NOT bump artifact-increment disciplines (spec-first cycle / strict-mode applications / grep-baseline / spec-time-grep-verification / cross-cycle-handoff) because they skip artifact drafting events (no Phase 0 audit file, no Plan v1, no closure narrative artifact). This is per the new sub-rule banked under `### Discipline-count-bump-needs-explicit-justification` at P0.R1 Phase 0 verdict: **`WONTFIX-closures-skip-artifact-increment-discipline-counts`**.

**Per-artifact-arithmetic-drift-survives-grep-baseline 4th instance averted** — explicit enumeration here makes the +3 jump grep-verifiable; no arithmetic drift surfaces at closure-audit.

---

## §2. D-decisions — unchanged from Plan v1 §2

D1 contract lock from `tests/p0_r1_onnx_session_wrap_plan_v1.md` §2.1-§2.2 stays canonical. No edits.

---

## §3. Test surface — unchanged at 4 anchors NARROW band mid 4

Plan v1 §3 LOCK at 4 anchors stays canonical. Q5 prediction: 0% ON-TARGET at closure-actual 4 anchors.

---

## §4. Closure-actual projection — unchanged from Plan v1 §4

Plan v1 §4 honest-count commitment (15th instance MADE) stays canonical. Plan v2 does NOT re-make the commitment — Plan v1 §4 is the canonical MADE event per the locked precedent (final-Plan-version-locks-the-band rule from P0.B2 STRICT precedent).

NARROW band [3.4, 4.6] mid 4 (unchanged):

| Closure-actual | Math vs mid 4 | Disposition | Doctrine effect |
|---|---|---|---|
| ≤2 anchors | ≤-50% | FALSIFICATION | DEMOTES 13 → 12 |
| 3 anchors | -25% | SLIGHT-DRIFT-DOWN | HOLDS at 13 |
| **4 anchors (Plan v1 LOCK)** | **0%** | **ON-TARGET** | **BUMPS 13 → 14** |
| 5 anchors | +25% | SLIGHT-DRIFT-UP | HOLDS at 13 |
| ≥6 anchors | ≥+50% | FALSIFICATION | DEMOTES 13 → 12 |

---

## §5. Closure-narrative paste-template — UPDATED for Plan v2 +1 artifact

### §5.1 CLAUDE.md line ~3 (updated per Plan v2 4-artifact cycle)

When P0.R1 closes, prepend above P0.S8 entry. KEY DELTAS from Plan v1 §5.1 marked with ← Plan v2 update:

```
| **P0.R1 (ONNX session.run() wrap for AdaFace embed + lazy CPU-EP fallback) CLOSED 2026-05-XX** — Closes the unwrapped vision.py:334 session.run() that crashed recognition path on CUDA OOM. Single D1 contract: wrap embed() in try/except + lazy CPU-EP session construction + cached as instance singleton + None return on cascading failure. Mirrors core/audio.py:170-180 Smart-Turn wrap pattern. **D1 (LOAD-BEARING)**: `core/vision.py::FaceEmbedder.embed()` wraps `self._session.run(None, {self._input_name: img})` in try/except; on RuntimeError catch, lazily builds `self._cpu_session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])` (one-time ~1s build cost; ~80MB memory cost; cached for process lifetime); retries session.run with CPU; returns transparent embedding. On cascading CPU failure: log + return None (caller treats as recognize-miss via existing P0.5/P0.S1 None-handling paths). Type annotation `np.ndarray` → `np.ndarray | None`. **D1 caller-site None-safety mitigations** (Plan v2 §1.2 corrected enumeration): 4 pipeline.py sites + 1 enroll.py site each gain explicit `if embedding is None:` guard at Phase 1 implementation (pipeline.py:3356 first_boot_flow + 3429 enrollment_flow + 6573 background vision loop + 6965 camera fallback; enroll.py:80 CLI exit). 6th caller `core/vision_channel.py:247` already None-safe per Session 48 wiring. **Total P0.R1 LOGICAL ANCHORS: 4** (Plan v1 §3 LOCK EXACT MATCH at exact mid 4 NARROW band [3.4, 4.6]). **Q5 closure under MID-RANGE methodology**: auditor mid 4, Plan v1 lock 4, **closure actual 4** (0% ON-TARGET exact mid; 6+ consecutive 0% exact-mid streak per `Doctrine-prediction-precision-improving-over-arc` sub-observation continues). Doctrine `### Phase-0-granular-decomposition-enables-accurate-estimates` **BUMPS 13 → 14 SUPPORTING INSTANCES**. Plan v1 §4 honest-count commitment HONORED — **16th instance of `Explicit-closure-honest-count-commitment` discipline** (15th MADE at Plan v1 §4, 16th HONORED at closure per STRICT separation). **4/4 deliberate-regression confirmations PASSED** (a/b/c/d per §2.2). **`### Zero-precision-items-at-auditor-review` 8 → 10 instances** (Phase 0 9th + Plan v2 10th if cleared; Plan v1 surface BLOCKED by PI #1 enumeration undercount → cycle escalated to Plan v2). **6th OPTIONAL-Plan-v2 proof case stays at 5 — BLOCKED at this cycle** ← Plan v2 update (auditor Plan v1 review surfaced PI #1 enumeration drift; cycle escalated; sub-rule track record stays at 5; P0.R1 does NOT bank 6th case). **NEW informal observation banked**: `Pre-audit-quantifier-precision-refined-by-grep` 1 instance (architect-memory only — pre-audit "every session.run()" overstated; grep verified 1/2 sites already wrapped; quantifier-precision error distinct from sub-pattern A wrong-premise). **NEW sub-rule banked under `### Discipline-count-bump-needs-explicit-justification`**: `WONTFIX-closures-skip-artifact-increment-discipline-counts` (locked at P0.R1 Phase 0 verdict). **`Plan-v1-Pass-2-grep-undercount` 4 → 5 instances** ← Plan v2 update (2 consecutive cycles P0.S9 + P0.R1 where auditor Pass-2 verification surfaced Plan v1 §1.1 enumeration drift; operational-rule extension candidacy reinforced; threshold 5+ ≈ formalization candidate at next instance). **NEW informal observation candidate**: `feedback_zero_precision_items_pre_closure_predictions.md` — architect's pre-Plan-v1-review predictions of "APPROVED 0 items" blocked at Plan v1 review for 2 consecutive cycles (P0.S9 arithmetic drift + P0.R1 enumeration drift); architect-memory only; watch 3+ consecutive blocked-by-PI cycles for operational-rule formalization. **Strict-industry-standard mode 52 → 56 applications + 15 → 16 closures** ← Plan v2 update (was 55; Plan v2 is 4th artifact: Phase 0 + Plan v1 + Plan v2 + closure × +1 each). Spec-first review cycle 62 → 66-for-66 at closure ← Plan v2 update (was 65; Plan v2 is 4th artifact). **`### Grep-baseline-before-drafting` 19 → 23 instances** ← Plan v2 update (was 22; Plan v2 is 4th artifact). **Cross-cycle-handoff transparency precedent 25 → 29** ← Plan v2 update (was 28). **Spec-time grep-verification 29 → 33 instances** ← Plan v2 update (was 32). **Twin-filename pitfall 14th preventive event already honored at Phase 0** (no doctrine count bump per locked enumeration rule). **Cumulative suite**: 2613 → 2617 (+4 new D1 anchors as 4 separate test functions in `tests/test_p0_r1_onnx_session_wrap.py`).
```

Key Plan v2 corrections embedded in §5.1:
- Caller-site enumeration: 4 pipeline.py sites (was implied as 3) + enroll.py + vision_channel.py (already safe)
- "6th OPTIONAL-Plan-v2 proof case stays at 5 — BLOCKED at this cycle" (was "6th OPTIONAL-Plan-v2 proof case" — P0.R1 escalated to Plan v2; doesn't qualify as proof case)
- All artifact-increment discipline counts +1 (4 artifacts: Phase 0 + Plan v1 + Plan v2 + closure)
- `Plan-v1-Pass-2-grep-undercount` 4 → 5 instances banked
- NEW architect-memory observation candidate: `feedback_zero_precision_items_pre_closure_predictions.md`

### §5.2-§5.4 parent + subdir `complete-plan.md` + `to_be_checked.md`

Per P0.S8/P0.S9 precedents. Twin-filename pitfall discipline at status flip (parent + subdir). Counts mirror §5.1 corrections above.

### §5.5 Memory files

- `feedback_explicit_closure_honest_count_commitment.md`: bump 14 → 16 (Plan v1 §4 MADE 15th + closure HONORED 16th per STRICT).
- `feedback_phase_0_zero_precision_items_at_auditor_review.md`: bump 8 → 10 (Phase 0 9th + Plan v2 10th if cleared — Plan v1 surface BLOCKED).
- `feedback_doctrine_prediction_precision_improving_over_arc.md`: extend 5+ → 6+ cycle 0% streak.
- `feedback_plan_v1_pass2_grep_undercount.md`: bump 4 → 5 instances.
- **NEW** `feedback_pre_audit_quantifier_precision_refined_by_grep.md`: 1 instance (architect-memory only — banked at Phase 0 verdict).
- **NEW** `feedback_zero_precision_items_pre_closure_predictions.md`: architect-memory observation candidate (1 instance candidate — 2 consecutive blocked-by-PI cycles P0.S9 + P0.R1; watch 3+ for formalization).
- MEMORY.md index refresh.

---

## §6. Cross-spec impact analysis — unchanged from Phase 0 §5 + Plan v1 §6

---

## §7. Quality gate checklist — Plan v2 absorbs PI #1 cleanly (11/11)

Per strict-mode 11-gate floor (updated for Plan v2):

1. ✅ Phase 0 audit completed + auditor-approved with 0 PIs (9th `Zero-precision-items` instance at Phase 0 surface).
2. ✅ Plan v1 surfaced PI #1 from auditor Pass-2 verification (§1.1 enumeration undercount).
3. ✅ Plan v2 absorbs PI #1 proactively via Option (a) minimal correction (§1.1 + §1.2 + §1.4 + §1.5 baseline clarification).
4. ✅ D-decision contract unchanged from Plan v1 §2.1.
5. ✅ Pre-mortem coverage — 10 failure modes documented at Phase 0 §6.
6. ✅ Multi-direction invariant trace per D-decision — Phase 0 §7.
7. ✅ Cross-spec impact analysis — Phase 0 §5.
8. ✅ Spec-time grep-verification (Pass-1 + Pass-2 + Pass-3 at Plan v2) — Phase 0 §1-§2 (Pass-1) + Plan v1 §1.1 (architect Pass-2 — undercount) + auditor Plan v1 verdict (Pass-2 verification cross-check — caught the undercount) + Plan v2 §1.1 (Pass-3 corrective enumeration).
9. ✅ Honest-closure-actual-count commitment made at Plan v1 §4 — 15th instance; Plan v2 inherits canonical commitment.
10. ✅ Deliberate-regression check protocol — Plan v1 §2.2 enumerates 4 induced reverts; Plan v2 inherits unchanged.
11. ✅ Closure-narrative paste-template ready — Plan v2 §5 5-surface template + §3 band-table (counts corrected for Plan v2 4th artifact).

---

## §8. Discipline counts at Plan v2 close (CORRECTED per PI #1 absorption + baseline clarification)

| Discipline | Pre-P0.R1 baseline | Phase 0 close (+1) | Plan v1 close (+2) | Plan v2 close (+3) |
|---|---|---|---|---|
| Spec-first review cycle | 62 | 63 | 64 | **65** ✓ |
| Strict-industry-standard mode (applications) | 52 | 53 | 54 | **55** ✓ |
| Strict-industry-standard mode (closures) | 15 | 15 | 15 | 15 (closure event pending) |
| `### Phase-0-granular-decomposition-enables-accurate-estimates` | 13 supporting | 13 | 13 | 13 (closure-actual pending; ON-TARGET candidate at 4 anchors → bump 13 → 14) |
| `### Phase-0-catches-wrong-premise` | **12** (per Plan v2 §1.5 enumeration: 9 post-P0.S9 + 3 from P0.S10/P0.S11/P0.8 WONTFIX bumps earlier today) | 12 | 12 | 12 (sub-pattern A NOT triggered at P0.R1 per auditor Phase 0 verdict; quantifier-precision error distinct) |
| `### Twin-filename-pitfall-prevention` | 7 + 4 op rules | 7 | 7 | 7 (14th preventive event already honored at Phase 0; doctrine count holds per locked enumeration rule) |
| `### Grep-baseline-before-drafting` | 19 | 20 | 21 | **22** ✓ |
| `### Zero-precision-items-at-auditor-review` | 8 | **9** ✓ (Phase 0 surface fired) | 9 (Plan v1 surface BLOCKED by PI #1; doctrine does NOT fire) | 9 (Plan v2 audit pending; if 0 items → 10th at Plan v2 surface) |
| Deferred-canary | 17th in-flight | 17 | 17 | 17 (closure event pending) |
| Auditor-Q5-estimates-trail-grep | 18 banked | 18 | 18 | 18 (closure event pending) |
| Cross-cycle-handoff transparency precedent | 25 | 26 | 27 | **28** ✓ |
| Architect-reads-production-code-before-sign-off | 12 banked (P0.S9 closure 11 + +1 from P0.S10/P0.S11/P0.8 cluster verification by architect — actually no, those were architect closure-audit events for WONTFIX cycles, each gets +1 architect-reads-production-code-before-sign-off bump; 11 + 3 = 14 actually... wait, the discipline bumps on closure-audit events where architect verifies; for WONTFIX cycles the architect DID verify (via Phase 0 grep)) | 14 | 14 | 14 (closure-audit pending → bump 14 → 15 at closure) |
| Sub-pattern A (in `### Phase-0-catches-wrong-premise`) | 12 | 12 | 12 | 12 (not triggered at P0.R1) |
| Spec-time grep-verification | 29 | 30 | 31 | **32** ✓ |
| Discipline-count-bump-needs-explicit-justification | 11 preventive | 11 | 11 | 11 (+ NEW sub-rule WONTFIX-closures-skip-artifact-increment-discipline-counts banked at Phase 0; Plan v2 §1.5 also exercises the discipline) |
| Convention-drift-on-discipline-counts | 5 | 5 | 5 | 5 |
| Per-artifact-arithmetic-drift-survives-grep-baseline | 3 | 3 | 3 | 3 (4th instance averted at Plan v2 §1.5 baseline clarification — explicit enumeration prevents drift; same prevention-shape as Convention-drift's preventive purpose) |
| `Explicit-closure-honest-count-commitment` | 14 | 14 | **15** ✓ (Plan v1 §4 commitment MADE) | 15 (canonical commitment; Plan v2 does NOT re-make) |
| `Auditor-catches-Q5-math-at-plan-review` | 2 | 2 | 2 | 2 |
| `Plan-v1-Pass-2-grep-undercount` | 4 | 4 | 4 | **5** ✓ (Plan v2 §1.4 banking — 2 consecutive cycles P0.S9 + P0.R1; operational-rule extension candidacy reinforced) |
| `Bug-fix-cycles-surface-discipline-edges` | 1 | 1 | 1 | 1 |
| `Auditor-adjudication-drift-clarified-by-architect` | 3 | 3 | 3 | 3 |
| `Stale-TODO-marker-after-work-complete` | 2 | 2 | 2 | 2 |
| `Board-meeting-attack-premise-needs-grep-verification` | 1 | 1 | 1 | 1 |
| `User-WONTFIX-after-design-dialogue` | 1 | 1 | 1 | 1 |
| `Doctrine-prediction-precision-improving-over-arc` | 5+ cycle 0% streak | 5+ | 5+ | 5+ (Plan v1/v2 LOCK at exact mid 4; extends to 6+ at closure if 4 anchors hold) |
| `Auditor-catches-doctrine-overlap-at-elevation-prep` | 1 (resolved at P0.S8 closure) | 1 | 1 | 1 |
| `Spec-internal-line-wrap-vs-substring-test-mismatch` | 1 (P0.S8) | 1 | 1 | 1 |
| `Tracking-row-stays-open-post-completion` | 3 (threshold reached at P0.8 WONTFIX) | 3 | 3 | 3 |
| `Pre-audit-quantifier-precision-refined-by-grep` | 0 | **1** ✓ (NEW banked at Phase 0 surface) | 1 | 1 |
| **NEW** `Zero-precision-items-pre-closure-predictions-blocked` | 0 | 0 | 0 | **1** ✓ (NEW banked at Plan v2 §1.4 — architect-memory candidate; watch 3+ for formalization) |
| OPTIONAL-Plan-v2 proof case (sub-rule under `### Zero-precision-items`) | 5 cases | 5 | 5 | 5 (closure-conditional 6th proof case BLOCKED — Plan v1 surfaced 1 PI; cycle escalated to Plan v2) |
| `### Induction-surfaces-invariant-gaps` | 9 | 9 | 9 | 9 (closure-conditional bump pending if induction protocol fires real gap at Phase 5) |

**Cells marked ✓ are bumped at this Plan version's surface per +1-per-artifact convention.**

**Key Plan v2 baseline-count clarifications:**
- `### Phase-0-catches-wrong-premise` pre-P0.R1 baseline = 12 (per §1.5 enumeration: 9 post-P0.S9 + 3 from P0.S10 + P0.S11 + P0.8 WONTFIX bumps earlier today)
- `Tracking-row-stays-open-post-completion` baseline = 3 (per same 3 WONTFIX cluster)
- WONTFIX closures do NOT bump artifact-increment disciplines (per new sub-rule)

---

## §9. Open questions for auditor — 0

Plan v2 absorbs PI #1 cleanly. No new open questions. Architect prediction: **APPROVED 0 items at Plan v2 review** → 10th instance of `### Zero-precision-items-at-auditor-review` fires at Plan v2 surface (extending Plan-vN enumeration rule precedent from P0.S9). Cycle ships to developer.

---

## §10. Implementation handoff readiness — UPDATED for §1.2 corrected enumeration

Developer contract from Plan v1 §10 updated per §1.2 corrected enumeration:

- **Scope:** D1 per §2.1 (single D-decision, ~10 LOC in `core/vision.py`) + caller-site None-safety mitigations at 5 caller sites (4 pipeline.py + 1 enroll.py) per §1.2.
- **Estimated effort:** 2 hours (D1 production code ~30 min + 5 caller-site None guards ~30 min + 4 anchor tests ~30 min + deliberate-regression protocol ~20 min).
- **Files touched:**
  - `core/vision.py` (D1 production code)
  - `pipeline.py` (4 caller-site None guards at lines ~3356, 3429, 6573, 6965)
  - `enroll.py` (1 caller-site None guard + clean exit at line ~80)
  - NEW `tests/test_p0_r1_onnx_session_wrap.py` (4 anchor tests)
- **Out of scope (Plan v2 explicit):** `core/vision_channel.py:247` (6th caller; already None-safe per Session 48 wiring); `core/db.py::recognize()` + `add_embedding()` (downstream consumers, not callers; already handle None per existing P0.5 + P0.S1 infrastructure).
- **Phase 1 (~30 min)**: D1 production code in core/vision.py (init attrs + embed() refactor with try/except + lazy CPU-EP build + cascading None return). Run existing test suite to verify no regressions.
- **Phase 2 (~30 min)**: 5 caller-site None guards at the 4 pipeline.py + 1 enroll.py sites per §1.2.
- **Phase 3 (~30 min)**: 4 anchor tests in tests/test_p0_r1_onnx_session_wrap.py per Plan v1 §2.1.
- **Phase 4 (~20 min)**: §2.2 deliberate-regression confirmations (a/b/c/d all must fire correctly + revert cleanly).
- **Phase 5 (~30 min)**: closure narrative + 5-surface landing + memory bankings + architect closure-audit.

---

## §11. Open invariants — unchanged from Plan v1 §11

---

## §12. No doctrine elevation candidacy at P0.R1 — unchanged from Plan v1 §12

Sub-pattern A NOT triggered at P0.R1 (per auditor Phase 0 verdict). `### Phase-0-catches-wrong-premise` count holds at 12.

---

**End of Plan v2.** Ready to forward to auditor.

**Architect prediction:** **APPROVED 0 items at Plan v2 review** → ship to developer with D1 contract from Plan v1 §2 + corrected 5-caller-site mitigations per Plan v2 §1.2 + updated discipline counts at closure per Plan v2 §5.1. `### Zero-precision-items-at-auditor-review` fires at Plan v2 surface (10th instance) IF this prediction holds.
