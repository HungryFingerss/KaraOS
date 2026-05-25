# P0.S7 Plan v1 — privacy_critical marker + CI enforcement + AST tripwire (Pass-2 enumeration locked)

**Phase 0 base:** `tests/p0_s7_privacy_critical_audit.md` (auditor APPROVED with 4 Plan v1 precision items + twin-filename pitfall doctrine elevation candidate flag). Plan v1 absorbs:
- **P1** Pass-2 grep to lock exact test enumeration count.
- **P2** D3 CI: LOCK **dual-step** (existing default excludes privacy_critical; NEW dedicated step).
- **P3** D3 fail-on-skip: LOCK **`-rs` + grep + fail-if-count>0** (no plugin).
- **P4** D2 marker convention: LOCK **most-granular-applicable** (function-level default; class-level when ALL tests in class privacy; module-level only when ALL tests in file privacy).
- **Twin-filename pitfall doctrine elevation pre-draft** at closure (5-instance threshold reached).

All Phase 0 D-decisions (D1-D4) stand UNCHANGED. Plan v1 locks application details + provides exhaustive enumeration table.

---

## §1. P1 — Pass-2 grep enumeration (LOCKED)

**Total: 129 test sites + 39 marker placements (8 module-level + 4 class-level + 27 function-level).**

### §1.1 Module-level marker placements (8 files)

These files contain ONLY privacy-critical tests. Apply `pytestmark = pytest.mark.privacy_critical` at module top after imports.

| File | Test count | Rationale |
|---|---|---|
| `tests/test_p0_s4_privacy_level_invariants.py` | 8 | P0.S4 privacy_level whitelist invariants; all tests are write-path validation + STATIC_MAP invariant |
| `tests/test_p0_s7_phase2.py` | 8 | P0.S7 D-A SHARED CONTEXT block; all 8 tests verify cross-person context construction + disputed-caller gates + flag-off |
| `tests/test_p0_s7_phase3.py` | 3 | P0.S7 D-A Phase 3 AST tripwires (log_turn audience helper + disputed_guard_present + facedb signature) |
| `tests/test_p0_s7_db.py` | 8 | P0.S7.D-B Kuzu v3 schema bump; all tests verify privacy_level edge attribute + find_shared_entities filters + every-caller-passes |
| `tests/test_p0_s7_5.py` | 15 | P0.S7.5 bundled-queue canary fixes; all tests verify visitor alert persistence + shared context fallback + known speaker block + HONESTY POLICY fabricated-absence + nudge gating |
| `tests/test_p0_s7_1_observability.py` | 4 | P0.S7 D-A observability tests; all observe shared_context emit per outcome + brain context summary format |
| `tests/test_p0_s7_2_phase1.py` | 2 | P0.S7.2 cross-session retrieval γ honesty bullet |
| `tests/test_p0_s7_2_phase2.py` | 12 | P0.S7.2 cross-session retrieval κ multi-person extraction (7 top-level + 5 class methods) |

**Subtotal: 60 tests covered by module-level marker.**

`tests/test_p0_s7_2_phase3.py` excluded — file contains only a `_build_test_orchestrator` helper, no tests. Plan v1 §6 closure-narrative naming.

### §1.2 Class-level marker placements (4 classes in `test_brain_agent.py`)

These classes contain ONLY privacy-critical tests. Apply `@pytest.mark.privacy_critical` decorator at class definition.

| Class | Test count | Rationale |
|---|---|---|
| `TestPrivacyFilter` | 9 | Privacy_level tagging + filter_facts_for_requester legacy + semantic_search filters |
| `TestBrainDBQueryKnowledgeFor` | 6 | `query_knowledge_for` with `_visibility_clause` SQL composition |
| `TestPrivacyIsolationE2E` | 11 | 3-persona end-to-end isolation (S109 closure of Phase 3A arc) |
| `TestVisitorAlert` | 13 | G5a/G5b visitor alert + S97 stranger promotion + S105 safety-flags + S114 dedup |

**Subtotal: 39 tests covered by class-level marker.**

### §1.3 Function-level marker placements (27 standalone tests)

**`test_pipeline.py` standalone (24 tests):**

```
1. test_privacy_levels_exhaustive_and_frozen
2. test_privacy_default_is_personal_fail_closed
3. test_privacy_static_map_values_valid
4. test_visibility_clause_best_friend_excludes_only_system_only
5. test_visibility_clause_non_best_friend_sees_public_own_personal_not_household
6. test_visibility_clause_no_best_friend_id_acts_as_non_privileged
7. test_visibility_clause_never_permits_system_only
8. test_visibility_clause_composes_cleanly_with_and
9. test_visibility_clause_params_align_with_placeholders
10. test_search_memory_description_covers_cross_person_recall
11. test_cross_person_excerpts_disputed_best_friend_labeled_disputed
12. test_build_cross_person_excerpts_renamed
13. test_p0_s7_dc_cross_person_excerpts_enabled_flag_defaults_false
14. test_p0_s7_dc_build_cross_person_excerpts_call_site_guarded_by_flag
15. test_p0_s7_dc_build_room_block_section1_renders_disputed_identity
16. test_p0_s7_dc_build_room_block_section1_renders_best_friend_role
17. test_p0_s7_dc_brain_context_summary_room_field_repointed_to_active_sessions
18. test_p0_s7_dc_no_room_context_prepending_when_flag_off
19. test_s114_visitor_alert_dedup_updates_promoted_alerts
20. test_s114_visitor_alert_dedup_skips_unrelated_alerts
21. test_s116_query_knowledge_for_emits_privacy_audit_log
22. test_s116_classify_privacy_level_logs_static_map_path
23. test_s111_cross_person_excerpts_filter_by_session_boundary
24. test_s111_cross_person_excerpts_render_addressee_and_age
```

**`test_brain_agent.py` standalone class-method tags (3 methods inside non-privacy classes):**

| Class | Method | Rationale |
|---|---|---|
| `TestExtractionAgent` | `test_extract_system_prompt_emits_dual_attribute_for_safety_critical` | Safety-critical attribute extraction discipline (S105 Bug N) |
| `TestContradictionAgent` | `test_safety_critical_attribute_never_replaces` | Append-only enforcement on safety attrs (S105 Bug N) |
| `TestContradictionAgent` | `test_safety_critical_various_mentioned_attributes_blocked` | Pattern-coverage for safety attrs (8 mentioned_* shapes) |

**`tests/test_core_memory.py` function-level (3 of 9 tests):**

```
1. test_get_core_memory_for_privacy_cross_person_blocked
2. test_get_core_memory_for_best_friend_sees_personal
3. test_get_core_memory_for_attribute_whitelist
```

Other 6 tests in `tests/test_core_memory.py` are core-memory rendering / flag-gating / confidence-floor mechanics — NOT cross-person privacy. Module-level marker rejected per P4 most-granular-applicable.

**Subtotal: 30 function-level placements (24 + 3 + 3).**

**Grand total: 8 module + 4 class + 30 function = 42 marker placements covering 129 tests.**

Phase 0 §1.3 estimated 60-70 tests; Pass-2 grep landed 129. Difference = test_p0_s7_5.py (+11 vs estimate) + test_p0_s7_db.py (+4) + test_p0_s7_phase2.py (+1) + test_p0_s7_phase3.py (+2) + test_p0_s7_2_phase1.py +phase2.py (+14, missed entirely at Phase 0) + test_p0_s7_1_observability.py (+1) + test_pipeline.py p0_s7_dc fan-out (+4) + test_brain_agent.py classes (~+9 from finer count) — total +46 vs Phase 0 estimate. Pass-2 grep at Plan v1 is the right surface; Phase 0 estimate was rough-order-of-magnitude.

---

## §2. P2 — D3 dual-step CI architecture (LOCKED)

**Decision: dual-step approach in `.github/workflows/fast.yml`.**

### Step A (existing default, MODIFIED):
```yaml
- name: Pytest — fast subset (excludes privacy_critical)
  env:
    PYTHONIOENCODING: utf-8
    PYTHONUNBUFFERED: "1"
  run: |
    pytest tests/ \
      -m "not slow and not network and not models and not privacy_critical" \
      --maxfail=5 \
      -q
```

Existing step's `-m` clause extends with `and not privacy_critical` so privacy tests don't run twice.

### Step B (NEW, immediately after Step A):
```yaml
- name: Pytest — privacy_critical (strict, fail-on-skip)
  env:
    PYTHONIOENCODING: utf-8
    PYTHONUNBUFFERED: "1"
  run: |
    set -e
    # Run privacy_critical tests with strict marker enforcement.
    pytest tests/ \
      -m privacy_critical \
      --strict-markers \
      -W error::pytest.PytestUnknownMarkWarning \
      -rs \
      --tb=short \
      | tee /tmp/privacy_critical_output.txt
    # Fail-on-skip: any SKIPPED line in -rs output triggers exit 1.
    # P3 mechanism (LOCKED at Plan v1): zero-dependency post-pytest grep.
    if grep -q "^SKIPPED" /tmp/privacy_critical_output.txt; then
      echo "::error::Privacy-critical test was SKIPPED — this is a P0.S7 invariant violation"
      grep "^SKIPPED" /tmp/privacy_critical_output.txt
      exit 1
    fi
```

**Why dual-step:**
- Each test runs exactly ONCE (Step A excludes privacy_critical; Step B includes ONLY privacy_critical).
- Step B's failure is a distinct, named CI signal — operator immediately sees "privacy-critical tests failed" in CI output vs lost-in-noise generic failure.
- Step B's `set -e` + explicit exit-on-SKIPPED keeps the fail-loud discipline.

**Why NOT marker-presence-assertion-only (single-step alternative):**
- Single-step doesn't expose the privacy_critical signal to GitHub Actions UI.
- A marker-only check doesn't catch RUNTIME `pytest.skip()` calls inside test bodies; the dual-step + grep DOES catch this.

---

## §3. P3 — D3 fail-on-skip mechanism (LOCKED)

**Decision: `-rs` flag + post-pytest `grep "^SKIPPED"` + `exit 1` if any match.** Concrete shape locked in §2 Step B above.

**Why this approach (vs alternatives):**
- **vs `--no-skips` plugin:** zero new dependency. Plugins add maintenance surface; `-rs` is pytest-native.
- **vs `pytest-fail-on-skip` plugin:** same dependency-avoidance argument.
- **vs marker-presence-only:** marker-only doesn't catch runtime `pytest.skip(...)` calls inside test bodies. The runtime skip is the harder-to-catch drift class (developer comments out an assertion in a privacy test, replaces with `pytest.skip("temporarily")`, forgets to remove — Step B fails immediately).

**Concrete CI behavior:**
- Test passes → exit 0, Step B green.
- Test fails → pytest exit code non-zero, Step B fails.
- Test skipped → pytest exit code 0 BUT `-rs` reports "SKIPPED" line → grep matches → `exit 1` → Step B fails.
- Test xfailed → pytest exit code 0, "XFAIL" reported but NOT "SKIPPED" → grep doesn't match → Step B passes (xfail is intentional expected-fail; semantically different from skip).
- All tests collected pass → Step B exits cleanly.

---

## §4. P4 — D2 marker convention (LOCKED)

**Decision: most-granular-applicable convention.**

| Granularity | When to use | Examples |
|---|---|---|
| **Function-level** (`@pytest.mark.privacy_critical` above `def test_`) | DEFAULT — when a test sits in a mixed-purpose file alongside non-privacy tests | 24 tests in test_pipeline.py + 3 tests in test_core_memory.py + 3 method-level in test_brain_agent.py |
| **Class-level** (decorator above `class TestX`) | When ALL tests in the class are privacy-critical | TestPrivacyFilter (9 tests) + TestBrainDBQueryKnowledgeFor (6) + TestPrivacyIsolationE2E (11) + TestVisitorAlert (13) |
| **Module-level** (`pytestmark = pytest.mark.privacy_critical` at file top) | When ALL tests in the file are privacy-critical | 8 single-purpose privacy test files |

**Rationale:**
- Most-granular-applicable prevents incidental marker leakage. If a future PR adds a non-privacy test to `tests/test_p0_s7_phase2.py`, the module-level marker would incorrectly tag it. P4 says: at that point, the developer should REMOVE the module-level marker + add function-level markers to the existing privacy tests instead.
- D4 enumeration tripwire enforces the convention structurally — if a known privacy_critical-anchor test loses its marker (module-level removed without per-test re-tag), tripwire fires.
- Trade-off acknowledged: ~30 function-level decorators in test_pipeline.py is verbose. Acceptable cost for drift resistance.

---

## §5. D4 enumeration tripwire (concrete contract — auditor's §3.4 ask)

**Test file:** `tests/test_p0_s7_privacy_critical.py` (NEW)

### §5.1 `test_known_privacy_critical_classes_all_tagged`
- Anchor list (LOCKED at Plan v1):
  ```python
  _KNOWN_PRIVACY_CRITICAL_CLASSES = (
      ("test_brain_agent.py", "TestPrivacyFilter"),
      ("test_brain_agent.py", "TestBrainDBQueryKnowledgeFor"),
      ("test_brain_agent.py", "TestPrivacyIsolationE2E"),
      ("test_brain_agent.py", "TestVisitorAlert"),
  )
  ```
- AST-walk: for each `(file, class)` pair, parse file → find class definition → assert `@pytest.mark.privacy_critical` decorator is present on the class.
- Failure message: `f"Class {file}::{cls} is in the privacy_critical anchor list but missing the class-level @pytest.mark.privacy_critical decorator. Add it OR remove from anchor list with rationale."`

### §5.2 `test_known_privacy_critical_files_all_module_tagged`
- Anchor list:
  ```python
  _KNOWN_PRIVACY_CRITICAL_FILES = (
      "tests/test_p0_s4_privacy_level_invariants.py",
      "tests/test_p0_s7_phase2.py",
      "tests/test_p0_s7_phase3.py",
      "tests/test_p0_s7_db.py",
      "tests/test_p0_s7_5.py",
      "tests/test_p0_s7_1_observability.py",
      "tests/test_p0_s7_2_phase1.py",
      "tests/test_p0_s7_2_phase2.py",
  )
  ```
- AST-walk: for each file, parse → find module-level `pytestmark = pytest.mark.privacy_critical` (or `pytestmark = [..., pytest.mark.privacy_critical, ...]` if file already has other markers).
- Failure message: `f"File {file} is in the privacy_critical anchor list but missing module-level pytestmark. Add `pytestmark = pytest.mark.privacy_critical` at file top OR remove from anchor list."`

### §5.3 `test_known_privacy_critical_standalone_functions_all_tagged`
- Anchor list (24 + 3 + 3 = 30 entries):
  ```python
  _KNOWN_PRIVACY_CRITICAL_STANDALONE = (
      # test_pipeline.py
      ("test_pipeline.py", None, "test_privacy_levels_exhaustive_and_frozen"),
      # ... [24 entries from §1.3]
      # test_brain_agent.py method-level (parent class is NOT in §5.1)
      ("test_brain_agent.py", "TestExtractionAgent", "test_extract_system_prompt_emits_dual_attribute_for_safety_critical"),
      ("test_brain_agent.py", "TestContradictionAgent", "test_safety_critical_attribute_never_replaces"),
      ("test_brain_agent.py", "TestContradictionAgent", "test_safety_critical_various_mentioned_attributes_blocked"),
      # test_core_memory.py
      ("test_core_memory.py", None, "test_get_core_memory_for_privacy_cross_person_blocked"),
      ("test_core_memory.py", None, "test_get_core_memory_for_best_friend_sees_personal"),
      ("test_core_memory.py", None, "test_get_core_memory_for_attribute_whitelist"),
  )
  ```
- AST-walk: for each `(file, class_or_None, function)` tuple, parse → find function (top-level or class method) → assert function-level `@pytest.mark.privacy_critical` decorator present.
- Failure message: `f"Function {file}::{cls}::{fn} (or {file}::{fn} if class is None) is in the privacy_critical anchor list but missing function-level @pytest.mark.privacy_critical decorator."`

### §5.4 `test_no_unexpected_privacy_critical_marker_outside_anchor_lists` (inverse drift)
- AST-walk ALL test files in the repo (tests/ + top-level test_*.py).
- For each `@pytest.mark.privacy_critical` decorator found, verify the test is in one of §5.1-§5.3's anchor lists OR inside a file/class with module/class-level marker that IS in the anchor lists.
- Catch class: "developer tagged a non-privacy test by mistake / by copy-paste."
- Failure message: `f"Unexpected @pytest.mark.privacy_critical marker on {file}::{location}. Either (a) add to one of the anchor lists in tests/test_p0_s7_privacy_critical.py if intentional, OR (b) remove the marker if accidental."`

---

## §6. Forecast: Plan v1 test count

**~14 logical anchors mid-range (matches Phase 0 forecast; locks at auditor mid 15 band 12-18):**

- D1 (2): marker registered + docstring/spec anchor present.
- D2 (3): §5.1 confirms class-level marker + §5.2 confirms module-level marker + §5.3 confirms function-level marker.
- D3 (4): CI step exists + dual-step structure + `-rs` flag present + fail-on-skip grep present.
- D4 (4): §5.1 + §5.2 + §5.3 + §5.4 inverse drift detector.
- Cross-cutting (1): Phase 4 closure deliberate-regression — remove a marker from one test → §5.x fires correctly.

**Q5 forecast under auditor's locked band 12-18 mid 15:** 14 anchors vs mid 15 = **−6.7% vs mid** → **ON-TARGET** (within ±15%).

---

## §7. Multi-direction invariant trace (per D-decision)

Phase 0 §6 stands unchanged. Plan v1 additions:

### D2 invariants under most-granular-applicable (P4)
- **Forward:** D4 §5.1-§5.3 are the consumers; each AST-walks at a different granularity (class / module / function).
- **Backward:** existing test function/class/module definitions are the producers; markers are pure metadata additions.
- **Sideways:** future test additions in the 8 module-tagged files automatically inherit the marker via `pytestmark`. Future tests in mixed-purpose files (test_pipeline.py / test_brain_agent.py non-anchored classes / test_core_memory.py) require explicit function-level decorator — D4 §5.3 anchor list enforces.
- **Lifecycle:** marker is static metadata. Visible at every pytest collection.

### D3 invariants under dual-step + fail-on-skip (P2 + P3)
- **Forward:** CI fails LOUDLY on any privacy_critical test fail OR skip. Operator sees the specific test name in Step B output.
- **Backward:** Step B reads markers from D1 + D2 tags.
- **Sideways:** Step A's `-m "not privacy_critical"` extension means privacy tests don't double-run. Other workflows (slow.yml, security.yml, trufflehog.yml) don't interact.
- **Lifecycle:** every PR + every push to any branch triggers BOTH Step A (default) AND Step B (privacy_critical).

---

## §8. Quality gate checklist (11 gates — all explicit per auditor §3.8)

- **[APPLIES] Correctness** — invariants 4-axis traced in §7 + Phase 0 §6.
- **[APPLIES] Security** — drift-class invariant. P0.S7 IS fundamentally a security spec — the meta-invariant that privacy-critical tests continue running.
- **[N/A] Privacy** — explicit rationale: P0.S7 enforces meta-invariant that privacy tests run; it does NOT compute or filter user-visible privacy data. Tags are CI metadata, not user-visible state. The N/A here is the "this spec IS the privacy-tier discipline + sanitization is orthogonal to runtime privacy_level computation" framing per auditor §3.8.
- **[APPLIES] Performance** — CI adds Step B (~30-60s additional pytest invocation). Acceptable (fast.yml budget 5min; +60s = +20% — still under target).
- **[APPLIES] Observability** — Step B fails LOUDLY with named failing test in CI output. D4 tripwire failures name specific file + class/function.
- **[APPLIES] Test pyramid** — D1 (config), D2 (mechanical tag application), D3 (behavioral via CI run), D4 (structural AST tripwire). Multi-layer.
- **[APPLIES] Regression guards** — D4 §5.4 inverse drift detector + Phase 4 deliberate-regression confirmations.
- **[APPLIES] Pre-mortem** — 12 failure modes in Phase 0 §3 (above 5-10 floor).
- **[APPLIES] Multi-direction trace** — §7 + Phase 0 §6.
- **[APPLIES] Backward compat** — pure additive. Existing tests run unchanged.
- **[APPLIES] Doc updates** — 5-surface closure (CLAUDE.md + 2 complete-plan.md + to_be_checked + 2 memory files). Twin-filename pitfall doctrine elevation pre-draft IF closure ON-TARGET (architect's call at closure).

**Total: 10 APPLIES + 1 N/A (privacy, with rationale).** Matches P0.S5/P0.S6 canonical shape.

---

## §9. Twin-filename pitfall doctrine elevation pre-draft (per auditor's banking observation)

**At P0.S7 closure, if discipline still holds at 5+ instances + no silent rollbacks**, elevate to numbered CLAUDE.md doctrine. Verbatim pre-draft for reference:

```markdown
### Twin-filename-pitfall-prevention

When a project has two same-named files at different paths serving different
roles, status-flip operations + closure artifacts MUST disambiguate explicitly
at artifact-creation time. Discovered at P0.S2 closure (developer flipped
status at subdir but missed parent path; architect's
`### Architect-reads-production-code-before-sign-off` discipline caught it).
Subsequent closures (P0.S3, P0.S4, P0.S6, P0.S7) applied the discipline
preventively + held the line.

**Track record (5 instances at P0.S7 closure):**
- **P0.S2 closure (2026-05-20):** 1st instance — gap-catch. Developer status-flip
  missed parent `complete-plan.md`. Architect closure-audit caught.
- **P0.S3 closure (2026-05-20):** 2nd — successful prevention via locked
  pre-flight checklist.
- **P0.S4 closure (2026-05-20):** 3rd — preventive application at audit drafting.
- **P0.S6 closure (2026-05-21):** 4th — preventive (intent-gates vs
  secrets-management P0.S6 disambiguation).
- **P0.S7 audit (2026-05-21):** 5th — preventive at audit drafting
  (`p0_s7_privacy_critical_*` vs prior P0.S7 D-A through D-E family arc).

**Operational rules:**
1. When ANY filename has parent/subdir or earlier-cycle/current-cycle twins,
   use distinguishing suffix at artifact creation time. NEVER rely on path
   alone to differentiate.
2. Closure pre-flight checklist (locked at P0.S2): verify status-flip at BOTH
   paths before declaring spec closed.
3. Architect closure-audit reads the actual files at BOTH paths; never trusts
   developer's narrative alone for the status flip.

**Why this matters:**

Same-name twin files are confusion clusters. The convention "use distinct
suffix at creation time" prevents the entire class of "I'll fix it later"
status-flip drift. P0.S2's gap-catch + the next 4 cycles' preventive
applications demonstrate the discipline working as designed.

**Future instances** continue to be banked. The discipline matures rather
than re-elevating at higher thresholds.
```

**Architect's lean at closure:** elevate. 5-instance threshold matches the canonical `### Phase-0-catches-wrong-premise` cadence; discipline-stability evidence holds across every closure since P0.S2. Auditor's banking observation explicitly named this as a candidate.

---

## §10. Cross-spec impact analysis (LOCKED)

- **P0.S6** (CLOSED 2026-05-21): tool registries. Distinct invariant class. P0.S6 tests NOT in P0.S7 marker set.
- **P0.S5** (CLOSED 2026-05-21): wrap_user_input injection. Distinct (injection-defense ≠ cross-person-privacy). P0.S5 tests NOT in P0.S7 marker set.
- **P0.S4** (CLOSED 2026-05-20): `_visibility_clause` whitelist. **IS in P0.S7 marker set** — `tests/test_p0_s4_privacy_level_invariants.py` (8 tests) gets module-level marker.
- **P0.S3 / P0.S2 / P0.S1:** not cross-person privacy.
- **Earlier-closed P0.S7 family** (D-A through D-E + P0.S7.1/.2/.4/.5/.5.1/.5.2): ALL ARE cross-person privacy work. Their test files (8 files in §1.1) get module-level markers.

**No invariant impact on any closed spec.** P0.S7 is pure additive.

---

## §11. Banked dispositions for auditor v1 review

- **Sub-pattern A `### Phase-0-catches-wrong-premise`:** STAYS at **6** instances.
- **`### Phase-0-granular-decomposition`:** STAYS at **8 supporting** (closure-conditional bump to 9 if P0.S7 lands ON-TARGET).
- **`### Spec-first review cycle`:** 34 → 35 at Plan v1 close per locked +1-per-artifact convention.
- **Strict-industry-standard mode:** 24 → 25 consecutive applications + 7 closures (in-flight to 8 at P0.S7 close).
- **Deferred-canary strategy:** 7th application in-flight.
- **Twin-filename pitfall:** **5 instances** (1 gap-catch + 4 preventions); doctrine elevation candidate at closure per §9 pre-draft.
- **`### Phase-0-catches-scope-expansion` informal:** STAYS at 2 instances (P0.S7 doesn't expand scope; R3 is partial-truth refinement).
- **Convention-drift-on-discipline-counts:** locked convention applied (counts increment +1 per artifact).

---

## §12. Open questions for auditor (2)

**Q1.** D4 inverse drift detector (§5.4) scope — should it AST-walk ALL test files in the repo? Or limit to `tests/` + top-level `test_*.py`? Architect's lean: limit to known test dirs (cheaper + sufficient). If auditor prefers exhaustive walk, Plan v2 absorbs.

**Q2.** Twin-filename pitfall doctrine elevation timing — pre-draft included in §9, but elevation lands at P0.S7 closure narrative. Should the doctrine text be locked NOW at Plan v1 (cleaner closure) OR can it iterate based on closure-cycle observations? Architect's lean: lock NOW at Plan v1 so closure is mechanical. If auditor prefers iteration window, Plan v2 absorbs.

---

**End of Plan v1.** Ready to forward to auditor for v1 review.
