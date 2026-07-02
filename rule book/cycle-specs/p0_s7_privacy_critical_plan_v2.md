# P0.S7 Plan v2 — Q1 + Q2 disposition locks + closure-conditional doctrine elevation language

**Plan v1 base:** `tests/p0_s7_privacy_critical_plan_v1.md` (auditor APPROVED with 2 Plan v2 precision items + cross-checks ratified). Plan v2 absorbs:
- **Q1 LOCK (a)** — D4 inverse walk scope = `tests/` + top-level `test_*.py`. Explicit `_INVERSE_WALK_PATHS` list + allowlist discipline (P0.S6 `_REGISTRY_ALLOWLIST` precedent).
- **Q2 LOCK (b)** — Doctrine elevation timing: pre-draft locked at Plan v1; formal elevation at closure with closure-conditional language matching canonical pattern.

All Plan v1 D-decisions (D1-D4) + P1 enumeration + P2 dual-step CI + P3 fail-on-skip + P4 most-granular-applicable convention stand UNCHANGED. Plan v2 is pure precision-item absorption + language refinement at §5.4 + §9.

---

## §1. Q1 LOCK — D4 inverse walk scope (a): `tests/` + top-level `test_*.py` only

### §1.1 Locked path scope

Replace Plan v1 §5.4 paragraph 1 ("AST-walk ALL test files in the repo (tests/ + top-level test_*.py)") with:

```python
# tests/test_p0_s7_privacy_critical.py
_INVERSE_WALK_PATHS: tuple[str, ...] = (
    # Top-level mixed-purpose test files (Python-side only)
    "test_pipeline.py",
    "test_brain_agent.py",
    # tests/ subdirectory (all Python-side test files)
    "tests/",
)

# Explicit-rejection paths (NOT scanned — documented rationale):
# - dog-ai-dashboard/        — Node.js (no Python tests possible)
# - node_modules/            — third-party; not our drift surface
# - .github/                 — CI config, not test files
# - bootstrap/               — one-shot offline pipeline; tests live under tests/
# - tools/                   — helper scripts; tests live under tests/
# - Any future top-level Python test file added with deliberate name pattern
#   (e.g., `eval_*.py`, `harvest_*.py`) is OPT-IN to the inverse walker
#   via _INVERSE_WALK_PATHS extension (mirror P0.S6 _REGISTRY_ALLOWLIST discipline).
```

### §1.2 Allowlist evolution discipline (P0.S6 precedent)

Adding a new path to `_INVERSE_WALK_PATHS` requires a one-line rationale comment naming WHY the path qualifies as a drift surface. Mirrors `_REGISTRY_ALLOWLIST` discipline locked at P0.S6 closure 2026-05-21.

### §1.3 Why `(a)` over alternatives

- **vs (b) exhaustive walk of entire repo:** privacy_critical is a Python-side test discipline. dog-ai-dashboard/ is Node.js (no `@pytest.mark.privacy_critical` decorators possible there). Exhaustive walk wastes CI time + adds false positives.
- **vs (c) tests/ only:** would MISS test_pipeline.py + test_brain_agent.py (the two top-level Python files holding 24 + 39 + 3 = 66 of the 129 enumerated tests).
- **vs (d) git-tracked test files only:** equivalent to (a) in practice; simpler to express via path list than `git ls-files` invocation.

### §1.4 Future-proofing

If a future privacy test lands outside `_INVERSE_WALK_PATHS` (e.g., new test file under `bootstrap/tests/`), D4 §5.1-§5.3 anchor lists STILL enforce marker presence for the anchored set. The inverse walker (§5.4) just doesn't scan for unexpected markers in unscanned paths. Same coverage-drift class as P0.S6's `_REGISTRY_ALLOWLIST` — locked path scope is acceptable trade-off.

---

## §2. Q2 LOCK — Doctrine elevation timing (b): pre-draft at Plan v1, formal elevation at closure

### §2.1 Canonical pattern

Per auditor's banking observation:
- `### Canary-surfaces-real-gaps` — pre-drafted at P0.S7.5.2 Plan v2 §7; formally elevated at P0.S7.5.2 closure.
- `### Phase-0-granular-decomposition-enables-accurate-estimates` — pre-drafted at P0.S3 Phase 0 §8; formally elevated at P0.S3 closure.
- `### Twin-filename-pitfall-prevention` — pre-draft at P0.S7 Plan v1 §9; formal elevation at P0.S7 closure (this spec).

### §2.2 Closure-conditional elevation language (REPLACES Plan v1 §9 final paragraph)

Plan v1 §9 final paragraph said:

> **Architect's lean at closure:** elevate. 5-instance threshold matches the canonical `### Phase-0-catches-wrong-premise` cadence; discipline-stability evidence holds across every closure since P0.S2. Auditor's banking observation explicitly named this as a candidate.

**Replace with:**

> **Closure-conditional elevation contract (locked at Plan v2 §2.2):**
>
> At P0.S7 closure, IF the discipline still holds at 5+ instances WITH discipline-stability evidence (every closure since P0.S2 applied the discipline; no silent rollbacks; no false positives where the discipline INCORRECTLY flagged a non-twin-filename situation), THEN elevate to `### Twin-filename-pitfall-prevention` numbered CLAUDE.md doctrine using the verbatim pre-draft text in this §9.
>
> IF discipline-stability is broken at closure (e.g., a 6th instance reveals the discipline was loose-counted, or a silent rollback surfaces during closure-audit), the elevation defers OR refines. Plan v3 absorbs OR the doctrine waits for a 6th confirming instance.
>
> **Falsification clause (locked at elevation, mirrors the other 3 elevated doctrines):** if a future instance reveals the 5-instance threshold was incorrectly counted (e.g., one of the 4 "preventive" applications wasn't actually preventive, it was a false-positive flag), the doctrine demotes back to architect-memory + the falsification banking applies.

### §2.3 Why `(b)` over alternatives

- **vs (a) lock at Plan v1, mechanical elevation at closure:** doesn't preserve the closure-cycle's final-verification structure. If Phase 1-5 implementation surfaces evidence that the discipline should be revised before elevation, mechanical elevation locks the wrong text.
- **vs (c) defer elevation entirely to a future cycle:** loses the canonical pattern's pre-draft-now-elevate-on-confirmation rhythm. Pre-draft serves as auditor advance approval; closure ratifies.

---

## §3. Discipline counts at Plan v2 close (UPDATED per auditor's verdict)

- **Spec-first review cycle:** 35 → 36 at Plan v2 close (per locked +1-per-artifact convention).
- **`### Phase-0-catches-wrong-premise`:** STAYS at 6.
- **`### Phase-0-granular-decomposition-enables-accurate-estimates`:** STAYS at 8 supporting; closure-conditional bump to 9 if P0.S7 lands ON-TARGET.
- **Strict-industry-standard mode:** 25 → 26 consecutive applications + 7 closures (in-flight to 8 at P0.S7 close).
- **Twin-filename pitfall:** 5 instances confirmed; **pre-draft LOCKED at Plan v1 §9**; formal elevation CONDITIONAL at closure per §2.2 contract.
- **Spec-time grep-verification:** 9 → **10 instances banked** at Plan v1 Pass-2 catch (auditor verdict explicit banking).
- **Cross-cycle-handoff transparency precedent:** 3 → **4th successful application** (Plan v1 cleanly absorbed all 4 precision items + 3 open question dispositions matching auditor lean; Plan v2 cleanly absorbs Q1 + Q2).
- **Discipline-count-bump-needs-explicit-justification:** STAYS at 5 preventive.
- **Convention-drift-on-discipline-counts:** locked convention applied at Plan v2 close (count from 35 → 36 per +1-per-artifact).
- **Deferred-canary strategy:** 7th application in-flight.
- **`### Phase-0-catches-scope-expansion` informal:** STAYS at 2 instances.

---

## §4. Quality gate checklist re-verification (no change from Plan v1 §8)

10 APPLIES + 1 N/A (privacy, with rationale). Matches P0.S5/P0.S6 canonical shape.

Plan v2 introduces zero new D-decisions; gate checklist unchanged from Plan v1 §8.

---

## §5. Open questions for auditor (0)

No new open questions at Plan v2. Q1 + Q2 from Plan v1 §12 locked per auditor's Plan v1 verdict.

**Architect prediction:** Plan v2 cleared with 0 precision items → OPTIONAL-Plan-v3 path per strict-mode §8 sub-rule. Ship to developer.

---

## §6. Implementation handoff readiness check (architect self-audit)

- ✅ All 4 D-decisions named with surfaces + contracts.
- ✅ All 4 precision items (P1-P4) absorbed at Plan v1 + locked at Plan v2.
- ✅ All 3 open questions (Plan v1 Q1-Q3) + 2 Plan v2 (Q1-Q2) locked with rationale.
- ✅ 11-gate checklist applied (10 APPLIES + 1 N/A privacy).
- ✅ Pre-mortem 12 modes above 5-10 floor.
- ✅ Multi-direction trace per D-decision.
- ✅ Cross-spec impact analysis (P0.S6 / P0.S5 / P0.S4 / earlier P0.S7 family).
- ✅ Q5 forecast under re-baselined mid-range methodology: 14 anchors vs auditor mid 15 = −6.7% ON-TARGET.
- ✅ Twin-filename pitfall doctrine elevation pre-draft locked with closure-conditional language (§2.2).
- ✅ D4 inverse walk scope locked with allowlist discipline (§1.2).

**Developer contract estimate (~2-3 hours, mostly mechanical):**
- **Phase 1** (~10 min): Register `privacy_critical` marker in `pytest.ini` (1 line + docstring).
- **Phase 2** (~60-90 min): Apply 42 marker placements per Plan v1 §1.1-§1.3 enumeration. Bulk find-replace + per-file pytest collection check.
- **Phase 3** (~20 min): Add Step B to `.github/workflows/fast.yml` per §2 dual-step structure; modify Step A's `-m` clause to exclude privacy_critical.
- **Phase 4** (~30-45 min): NEW `tests/test_p0_s7_privacy_critical.py` with 4 AST tripwires per Plan v1 §5.1-§5.4 + Plan v2 §1 (locked `_INVERSE_WALK_PATHS`).
- **Phase 5** (~20 min): full-suite green + 5-surface closure (CLAUDE.md + parent + subdir complete-plan.md + to_be_checked.md + 2 memory files) + twin-filename pitfall doctrine elevation per §2.2 closure-conditional contract.

---

**End of Plan v2.** Ready to forward to auditor for v2 sign-off (architect prediction: APPROVED 0 items → ship).
