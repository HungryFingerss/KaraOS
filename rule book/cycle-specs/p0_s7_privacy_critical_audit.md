# P0.S7 Phase 0 audit — Cross-person privacy regression tests must run on every PR

**Spec ID disambiguation:** P0.S7 in the **parent** `c:\Users\jagan\dog-ai\complete-plan.md` enumeration line 631 — "Cross-person privacy regression tests must run on every PR" `[OPEN]`. **DISTINCT from** the earlier closed P0.S7 = Phase 3B D-A SHARED CONTEXT block (closed 2026-05-18) AND all its sub-cycles (D-B / D-C / D-D / D-E / P0.S7.1 / P0.S7.2 / P0.S7.4 / P0.S7.5 / P0.S7.5.1 / P0.S7.5.2) whose artifacts live at `tests/p0_s7_*.md` + `tests/p0_s7_db_*.md` + similar. Filename `p0_s7_privacy_critical_*.md` is intentionally distinct — **5th twin-filename pitfall successful prevention**.

**Pre-audit premise (verbatim from parent complete-plan.md:633):**
> **Fix:** tag tests `@pytest.mark.privacy_critical`; CI fails if skipped or failing.

**Cadence prediction:** 4 D-decisions (predicted; medium D-count band) + HIGH application fan-out at test-tag surface (~50-70 test sites enumerated below) but MODERATE architectural fan-out (one marker per test; no per-site code logic) → predicted **v1 → v2 floor**. NOT v3 unless Pass-2 grep surfaces structural complexity beyond mechanical marker application.

---

## §1. Grep-verified architectural surface (Pass-1)

### §1.1 Marker infrastructure

- `pytest.ini` (4 lines): only 3 markers registered today — `network`, `slow`, `models`. **`privacy_critical` does NOT exist.** Registration is D1's surface.
- `@pytest.mark.privacy_critical` zero occurrences across repo (`grep -r "privacy_critical"` returned zero matches). No tests are tagged today.

### §1.2 CI infrastructure (P0.0 era, exists)

CLAUDE.md historical narrative said "no CI config exists" (Session ~2026-04-22 era) but P0.0 closed that gap. Current state:
- `.github/workflows/fast.yml` — every push + PR. Runs `pytest tests/ -m "not slow and not network and not models" --maxfail=5 -q`. **Privacy-critical tests would run by default** if marker is added (since they're not slow/network/models).
- `.github/workflows/slow.yml` — nightly + manual.
- `.github/workflows/security.yml` — weekly + on requirements.txt change.
- `.github/workflows/trufflehog.yml` — PR diff + scheduled full-history scan.

**CI gap:** the existing fast.yml runs privacy-critical tests but doesn't ENFORCE them as a distinct CI signal. If a future PR adds `@pytest.mark.skip` or `pytest.skip()` to a privacy test, fast.yml's `--maxfail=5` would allow up to 4 skips silently. **No dedicated CI step that uses `-m privacy_critical --strict-markers` and treats skip-as-failure.**

### §1.3 Privacy-critical test enumeration (Pass-1 grep, may extend at Pass-2)

**~50-70 tests across 10 files.** Authoritative anchor for the privacy_critical tag application:

**A. test_pipeline.py (top-level)** — **15 tests** spanning:
- 3 config invariants (`test_privacy_levels_exhaustive_and_frozen` + `test_privacy_default_is_personal_fail_closed` + `test_privacy_static_map_values_valid`)
- 6 `_visibility_clause` SQL helper tests (excludes_only_system_only / non_best_friend_sees_public_own_personal_not_household / no_best_friend_id / never_permits_system_only / composes_cleanly_with_and / params_align_with_placeholders)
- 1 `test_search_memory_description_covers_cross_person_recall` (S98 Bug B tool-desc tightening)
- 2 `test_cross_person_excerpts_*` (S66 dispute-precedence + S107 build-cross-person-renamed)
- 2 `test_p0_s7_dc_cross_person_excerpts_*` (D-C Stage 1 flag-gate)
- 2 `test_s114_visitor_alert_dedup_*` (S114 promoted-alert dedup)
- 2 `test_s116_*` (P0.S7.2 privacy audit log)
- 2 `test_s111_cross_person_excerpts_*` (S111 session boundary + addressee+age)

**B. test_brain_agent.py (top-level)** — **~25-30 tests**:
- `TestPrivacyFilter` class (~10 tests) — Extraction.privacy_level round-trips + filter_facts_for_requester legacy + semantic_search filters personal for non-owner
- `TestBrainDBQueryKnowledgeFor` class (~6 tests) — best_friend sees household/personal own + non-best_friend excluded
- `TestPrivacyIsolationE2E` class (**11 tests** per S109 narrative; 3 personas + mixed tiers end-to-end)
- `TestVisitorAlert` class (~3-5 tests) — G5a/G5b visitor alert + S114 dedup + S97 Fix 1 stranger-promotion
- 2 `test_safety_critical_*` (ContradictionAgent never-replaces safety-flagged attrs)

**C. tests/test_p0_s4_privacy_level_invariants.py** — **8 tests** (D1 write-path validation + D2 module-wide AST scan + D3 STATIC_MAP invariant from P0.S4 closure 2026-05-20)

**D. tests/test_p0_s7_phase2.py** — **7 tests** (SHARED CONTEXT block: multi-person / addressed_to / single-person None / flag-off None / disputed-caller None / empty-room_session_id None / injected_in_prompt / pipeline_call_sites)

**E. tests/test_p0_s7_phase3.py** — **1 test** (disputed_guard_present AST tripwire)

**F. tests/test_p0_s7_db.py** — **4 tests** (Kuzu privacy_level edge attribute + create_edge_threads + store_fact_threads + every_create_edge_caller_passes)

**G. tests/test_p0_s7_5.py** — **4 tests** (one-shot nudge / D2 fallback / fast path / visitor alert persistence)

**H. tests/test_p0_s7_1_observability.py** — **3 tests** (per-outcome log emit + [Brain] Context: format / last_shared_context_row_count assignment)

**I. tests/test_p0_s7_2_phase3.py** — **~1+ tests** (cross-session retrieval γ + κ from S95 Phase 3A.2)

**J. tests/test_core_memory.py** — **1 test** (`test_get_core_memory_for_privacy_cross_person_blocked` — owner-mode + non-owner branches per S110 P3.21 + S111 §4.6)

**Estimated total: ~60-70 privacy-critical tests.** Pass-2 grep at Plan v1 drafting may surface additional candidates (e.g., the `TestPrivacyFilter` class has more tests than the 10 estimated; full count happens at Plan v1).

### §1.4 Tag-drift surface

Without a structural enumeration, the marker assignment is human-judgment-only:
- **Drift class 1**: future PR adds new `test_*_privacy_*` in `test_brain_agent.py` but forgets `@pytest.mark.privacy_critical`. CI passes the new test under default markers but it's not in the privacy-critical CI signal.
- **Drift class 2**: future refactor renames a privacy-critical test or moves it to a different file. If the rename strips the marker (mechanical refactor tool / merge conflict), the test silently drops out of the privacy-critical signal.
- **Drift class 3**: a developer adds `@pytest.mark.skip` to a privacy-critical test during local debugging and forgets to remove it. Today's fast.yml `--maxfail=5` would absorb up to 4 such skips silently.

**Same coverage-drift class as P0.S6 (TOOL_PRIVILEGES + TOOL_INTENT_MAP + _TOOL_FALLBACKS + _TOOL_HANDLERS).** P0.S6 closed it with startup assertions + AST tripwires; P0.S7 will close it with a CI step + an enumeration tripwire.

---

## §2. Pre-audit premise check

**Parent complete-plan.md:633 premise:** "tag tests `@pytest.mark.privacy_critical`; CI fails if skipped or failing."

**Grep-verified verdict: PARTIAL-TRUTH ON-TARGET** for the application-half of the premise. The CI infrastructure is already in place (fast.yml runs on every PR); the marker registration + tag application + CI enforcement gap is real. **Missing from the premise:** structural drift protection (no enumeration tripwire is mentioned).

**Premise refinements adopted:**
- **R1:** marker registration is one-line in pytest.ini; tag application is mechanical across ~60-70 tests.
- **R2:** CI enforcement needs explicit step that uses `pytest -m privacy_critical --strict-markers -W error::pytest.PytestUnknownMarkWarning` AND treats `pytest.skip` / `pytest.xfail` as FAILURE (today's pytest default treats skip as pass).
- **R3:** P0.S7 scope EXTENDS to enumeration tripwire (architect's own Phase 0 finding — same shape as P0.S6's P3 AST-walk tripwire). Coverage drift WILL occur in a months-long codebase if not structurally locked. Same-cycle close per strict-mode §1.

**Sub-pattern A (`### Phase-0-catches-wrong-premise`)** does NOT apply. The premise's CORE (tag + CI + fail-loud) is correct. The half-truth (missing structural drift protection) is scope-precision similar to P0.S3/P0.S5/P0.S6 ON-TARGET-with-refinements. Doctrine count stays at **6**.

---

## §3. Pre-mortem (12 failure modes — strict-mode floor 5-10)

### §3.1 — D2 tag application: missing a privacy-critical test → silent CI under-coverage
**Risk:** Pass-1 grep enumerated ~60-70 tests; Pass-2 + Pass-3 will likely surface more. Missing tests from the application set is the "Bug-W-class regression silently slips through" anti-pattern that P0.S6 D2/D3/D4 startup assertions catch for tool registries.
**Mitigation:** D4 enumeration tripwire — structural test that AST-walks the privacy-critical test files + asserts every test function in the named classes/modules carries the marker. Drift detected at test-collection time, not at runtime.

### §3.2 — D3 CI step ordering vs other workflows
**Risk:** fast.yml today runs all tests excluding slow/network/models. Adding a SEPARATE privacy-critical job could double-count tests (run once in fast.yml's default + once in the privacy-critical step). Wasted CI cycles + slower turn-around.
**Mitigation:** add the privacy-critical step INSIDE fast.yml as a SECOND `pytest` invocation with `--strict-markers -m privacy_critical -W error::pytest.PytestUnknownMarkWarning` AND remove privacy_critical tests from the default invocation via `-m "not slow and not network and not models and not privacy_critical"`. Net: each test runs ONCE in CI; privacy-critical tests get their dedicated step.
**Alternative considered:** keep privacy_critical tests in the default invocation + add a separate ENFORCEMENT step that just asserts marker presence (no test re-run). Cleaner but less explicit signal in CI output. Plan v1 adjudicates.

### §3.3 — D3 skip-as-failure semantics
**Risk:** pytest's default treats `pytest.skip()` as a pass (test was correctly skipped). For privacy-critical tests, skip MUST be failure — the test was opted out, which is the exact drift class we're preventing.
**Mitigation:** the second pytest invocation uses `--strict-markers` (rejects unknown markers) + `-W error::pytest.PytestUnknownMarkWarning` (warnings → errors) + the test enumeration tripwire D4 (structurally enforces tag presence at AST level). For runtime skip detection: use pytest's `--no-skips` plugin OR custom conftest hook that fails-loud on any `pytest.skip` call within a privacy_critical-marked test.
**Plan v1 adjudication:** simpler approach is `-rs` (report skips) + post-pytest grep "SKIPPED" + fail if count > 0. Or pytest-fail-on-skip plugin. Lock at Plan v1.

### §3.4 — D4 enumeration tripwire scope
**Risk:** an AST tripwire that walks every test file in the repo is expensive (~1-2s additional test time). Limiting scope to KNOWN privacy-critical files is faster but introduces a maintainable list that itself can drift.
**Mitigation:** D4 splits into TWO checks: (a) for KNOWN privacy-critical test classes (locked anchor list in the tripwire test), assert every test method carries the marker; (b) for KNOWN privacy-critical test files, assert every top-level `def test_*` function carries the marker. Adding a new privacy-critical test in a covered file → auto-detected via (b); adding a new privacy-critical class in a non-covered file → manual addition to the anchor list (caught at code review).

### §3.5 — D2 tag application breaks existing test imports / collection
**Risk:** adding `@pytest.mark.privacy_critical` decorators across 60-70 test functions across 10 files involves edits to many files. Mistakes could break test collection (e.g., import error from misplaced decorator).
**Mitigation:** mechanical edit (one decorator per test). Phase 4 closure runs the full suite to verify zero collection errors. Pre-commit grep for "@pytest.mark.privacy_critical" placement (above `def test_` or above `class Test...`) catches typos.

### §3.6 — Class-level vs function-level marker placement
**Risk:** `TestPrivacyFilter`, `TestBrainDBQueryKnowledgeFor`, `TestPrivacyIsolationE2E`, `TestVisitorAlert` are CLASSES with multiple test methods each. Two options:
- (a) Class-level: `@pytest.mark.privacy_critical` above `class TestX` — applies to all methods. Less repetition.
- (b) Method-level: tag each `def test_*` method individually. More explicit, more verbose.
**Mitigation:** lean is (a) class-level for the 4 privacy-test classes; (b) method-level for the standalone `def test_*` functions in test_pipeline.py and elsewhere. Plan v1 locks the convention.

### §3.7 — pytest.ini marker docstring vs runtime semantics
**Risk:** `pytest.ini` marker registrations include a description after the colon (e.g., `network: test depends on a live...`). The description is documentation; it doesn't enforce anything at runtime.
**Mitigation:** D1 marker registration includes a descriptive comment block in pytest.ini PLUS the spec anchor (e.g., `privacy_critical: cross-person privacy regression. CI runs separately with --strict-markers + fail-on-skip. Spec: tests/p0_s7_privacy_critical_plan_v1.md`). Future maintainers grepping pytest.ini find the spec reference.

### §3.8 — Cross-spec impact: P0.S6 invariant preserved
**Risk:** P0.S6 closed yesterday (2026-05-21) with `tests/test_p0_s6_intent_gates.py` (19 tests). P0.S6 tests are TOOL-coverage invariants, NOT privacy-critical. Should they be tagged?
**Mitigation:** NO. The `privacy_critical` marker is for CROSS-PERSON-PRIVACY invariants (visibility_clause, query_knowledge_for, cross-person retrieval, visitor alert, safety-critical preservation, SHARED CONTEXT block). Tool-coverage invariants are CORRECTNESS invariants of a different kind. Plan v1 explicitly enumerates the boundary in §1.3 + the marker docstring.

### §3.9 — Multi-spec test files (test_pipeline.py is 16K+ lines)
**Risk:** `test_pipeline.py` has 15+ privacy-critical tests interspersed with hundreds of non-privacy tests. Tagging individual function decorators across 15 sites in one large file is error-prone.
**Mitigation:** Plan v1 commits to per-function tagging in test_pipeline.py (no class-level applies because tests aren't class-grouped there). Phase 2 implementation uses a structured sed/replace pattern + pytest collection check after each batch (e.g., 5 tags at a time).

### §3.10 — Plan-version cadence prediction
**Risk:** 4 D-decisions (medium-D) but ~60-70 application sites + AST tripwire complexity could push to v3. P0.S5 precedent: HIGH fan-out drove v3.
**Mitigation:** explicit prediction at Phase 0: v1 → v2 floor likely. Pass-2 grep at Plan v1 drafting may surface additional privacy-critical tests not in §1.3's count; if Pass-2 surfaces +10 tests or more, the count is still mechanically applied (not architectural complexity). v3 only triggered if structural complexity at D4 tripwire surfaces (e.g., needs to handle pytest's collection lifecycle).

### §3.11 — Cross-spec impact analysis (other privacy-touching surfaces)
**Risk:** P0.S6 (tool registries) doesn't touch privacy. P0.S5 (wrap_user_input) is injection-defense, not cross-person privacy. P0.S4 (privacy_level validation) IS cross-person — its 8 tests in `tests/test_p0_s4_privacy_level_invariants.py` ARE privacy_critical. P0.S2 (dashboard auth) is not cross-person. P0.S3 (env validation) is not cross-person.
**Mitigation:** P0.S4's 8 tests get the marker. Plan v1 §1.3 explicitly enumerates the inclusion.

### §3.12 — Pass-N grep-verification fatigue
**Risk:** even at MODERATE fan-out, multi-pass grep can surface residual tests. P0.S6 had architect Pass-2 catch (D4 _TOOL_HANDLERS); P0.S5 had developer Pass-3 + Pass-4 catches.
**Mitigation:** Plan v1 commits to Pass-1 enumeration as architect's best-effort. Auditor Pass-2 + developer Pass-3 expected. Convergence claimed only at closure, not at Plan v1.

---

## §4. D-decisions (4 decisions; all locked at Phase 0)

### D1 — Register `privacy_critical` marker in `pytest.ini`
- **Surface:** `pytest.ini:7` (immediately after `models:` marker).
- **Contract:** new marker definition with docstring naming scope (cross-person privacy regression) + CI enforcement clause + spec anchor (`tests/p0_s7_privacy_critical_plan_v1.md`).

### D2 — Apply `@pytest.mark.privacy_critical` to ~60-70 existing tests across 10 files
- **Surface:** 4 test classes (class-level tag) + ~30-40 standalone test functions (function-level tag) across:
  - `test_pipeline.py` (15 standalone functions)
  - `test_brain_agent.py` (4 classes + 2 standalone — TestPrivacyFilter + TestBrainDBQueryKnowledgeFor + TestPrivacyIsolationE2E + TestVisitorAlert + 2 safety-critical functions)
  - `tests/test_p0_s4_privacy_level_invariants.py` (8 functions OR module-level marker via `pytestmark = pytest.mark.privacy_critical`)
  - `tests/test_p0_s7_phase2.py` (7 functions OR module-level)
  - `tests/test_p0_s7_phase3.py` (1 function)
  - `tests/test_p0_s7_db.py` (4 functions OR module-level)
  - `tests/test_p0_s7_5.py` (4 functions OR module-level)
  - `tests/test_p0_s7_1_observability.py` (3 functions OR module-level)
  - `tests/test_p0_s7_2_phase3.py` (~1+ functions)
  - `tests/test_core_memory.py` (1 function — `test_get_core_memory_for_privacy_cross_person_blocked`)
- **Convention (locked at Plan v1):**
  - Class-level marker for the 4 privacy-test classes in test_brain_agent.py.
  - Module-level `pytestmark` for files whose entire purpose is privacy testing (test_p0_s4_privacy_level_invariants.py, test_p0_s7_phase2.py, test_p0_s7_db.py, test_p0_s7_5.py, test_p0_s7_1_observability.py).
  - Function-level marker for standalone privacy tests in mixed-purpose files (test_pipeline.py, test_brain_agent.py standalone, test_core_memory.py single test).

### D3 — Add dedicated CI step in `.github/workflows/fast.yml` that enforces privacy_critical
- **Surface:** new step after the existing "Pytest — fast subset" step.
- **Contract:**
  ```yaml
  - name: Pytest — privacy_critical (strict, fail-on-skip)
    env:
      PYTHONIOENCODING: utf-8
    run: |
      pytest tests/ \
        -m privacy_critical \
        --strict-markers \
        -W error::pytest.PytestUnknownMarkWarning \
        -ra \
        --tb=short
      # Post-pytest: fail-on-skip detection (treat skipped privacy tests as failures)
      if grep -q "SKIPPED" <<< "$(pytest tests/ -m privacy_critical --collect-only -q 2>&1)"; then
        echo "::error::Privacy-critical test was skipped — this is a P0.S7 invariant violation"
        exit 1
      fi
  ```
- **Optionally:** modify the existing "fast subset" step to also exclude `privacy_critical` so tests don't run twice. Plan v1 adjudicates the dual-step-vs-single-step choice per §3.2.

### D4 — Structural enumeration tripwire in `tests/test_p0_s7_privacy_critical.py`
- **Surface:** new test file.
- **Contract:** two AST-walk tests:
  - (a) `test_known_privacy_critical_classes_all_tagged` — locked anchor list of 4 classes (TestPrivacyFilter, TestBrainDBQueryKnowledgeFor, TestPrivacyIsolationE2E, TestVisitorAlert) + assert each has the marker (class-level OR `pytestmark`).
  - (b) `test_known_privacy_critical_files_all_tests_tagged` — locked anchor list of N files (the module-level-marker files from D2 above) + assert every `def test_*` in those files inherits the marker via `pytestmark`.
  - (c) `test_privacy_critical_standalone_function_anchor_list` — locked anchor list of standalone test functions across test_pipeline.py + test_brain_agent.py + test_core_memory.py + assert each carries the function-level marker.
- **Inverse (drift-detection):** for the standalone tests, AST-walk also asserts no UNexpected `@pytest.mark.privacy_critical` decorator outside the anchor list (catches "tagged a non-privacy test").

---

## §5. Forecast: Plan v1 test count

**~14 logical anchors mid-range, 11-17 outer range:**

- D1 (2): marker registered + docstring contains scope + spec anchor.
- D2 (3): N classes have class-level marker + N files have `pytestmark = pytest.mark.privacy_critical` + standalone functions tagged.
- D3 (4): CI step exists + uses `--strict-markers` + fail-on-skip detection present + ordering correct (after default-pytest step).
- D4 (4): tripwire test exists + classes anchor list locked + files anchor list locked + inverse drift detector (unexpected tag) fires correctly.
- Cross-cutting (1): Phase 4 closure deliberate-regression — remove a marker from one test → tripwire fires correctly.

Mid-range total = 14. **Q5 prediction:** auditor mid-range estimate band 9-17 mid 13; architect Plan v1 forecast 14 = +7.7% vs mid → ON-TARGET (within ±15%). Trajectory under re-baselined methodology continues slight-OVER mid pattern.

---

## §6. Multi-direction invariant trace (per D-decision)

### D1
- **Forward:** D3 CI step + D4 tripwire both depend on marker existing.
- **Backward:** none (D1 is the producer).
- **Sideways:** parallel writers to pytest.ini — none; pytest.ini is shared but markers section is append-only by convention.
- **Lifecycle:** module-load (pytest reads ini at collection) → marker visible at every test collection.

### D2
- **Forward:** D3 CI step queries this tag via `-m privacy_critical` filter; D4 tripwire AST-walks for marker presence.
- **Backward:** reads existing test function/class definitions (no production code touched).
- **Sideways:** test renames could strip the marker — D4 tripwire's inverse detector catches.
- **Lifecycle:** static at file level; tests run at every CI invocation.

### D3
- **Forward:** CI fails if marker tests fail OR are skipped. Operator sees the gap.
- **Backward:** reads D1 marker registration + D2 tag application.
- **Sideways:** other CI workflows (slow.yml, security.yml, trufflehog.yml) don't interact with this step.
- **Lifecycle:** runs on every PR + every push to any branch.

### D4
- **Forward:** test failure when a known privacy_critical-anchor test loses its marker or an unexpected test gains one.
- **Backward:** reads the locked anchor lists in the tripwire test source.
- **Sideways:** future privacy-test additions require anchor-list update; this is the natural drift point but it's at code-review attention level.
- **Lifecycle:** runs on every CI invocation as part of the default pytest set.

---

## §7. Cross-spec impact analysis

- **P0.S6** (CLOSED 2026-05-21): tool registries. Distinct invariant class (tool dispatch coverage vs cross-person privacy). P0.S6 tests are NOT privacy_critical.
- **P0.S5** (CLOSED 2026-05-21): wrap_user_input injection defense. Distinct (injection ≠ cross-person privacy). P0.S5 tests are NOT privacy_critical.
- **P0.S4** (CLOSED 2026-05-20): `_visibility_clause` privacy-level whitelist. **IS privacy_critical.** Its 8 tests in `tests/test_p0_s4_privacy_level_invariants.py` get the module-level marker.
- **P0.S3** (CLOSED 2026-05-20): env validation. Not privacy-critical.
- **P0.S2** (CLOSED 2026-05-20): dashboard auth + bind. Not cross-person privacy.
- **P0.S1** (CLOSED 2026-05-20): anti-spoof on every face match. Not cross-person privacy (auth surface, not visibility surface).
- **Earlier-closed P0.S7 family** (D-A through D-E, P0.S7.1, P0.S7.2, P0.S7.5, P0.S7.5.1, P0.S7.5.2): all touched cross-person privacy retrieval. Their tests in `tests/test_p0_s7_*.py` are privacy_critical and get the marker.

**No invariant impact on any closed spec.** P0.S7 is pure additive — markers + CI step + tripwire. No production code touched.

---

## §8. Quality gate checklist (11 gates per strict-mode §4) — pre-Plan-v1 disposition

- **[APPLIES] Correctness** — invariants 4-axis traced in §6.
- **[APPLIES] Security** — drift-class invariant. A privacy-critical test silently dropped = exact regression class P0.S7 is meant to prevent. P0.S7 IS fundamentally a security spec.
- **[N/A] Privacy** — no new facts/state; markers + CI config are not user-visible.
- **[APPLIES] Performance** — CI cost: ~30-60s additional pytest invocation for the privacy_critical subset. Acceptable (fast.yml total budget 5min; adding 30s is 10% increase).
- **[APPLIES] Observability** — CI step output names which tests failed/skipped. AssertionError messages in D4 tripwire name which test class/function is missing the marker.
- **[APPLIES] Test pyramid** — D1 (config), D2 (tag application = mechanical), D3 (CI step = behavioral via PR), D4 (structural AST tripwire). Multi-layer coverage.
- **[APPLIES] Regression guards** — D4 tripwire IS the regression guard. Plus Phase 4 deliberate-regression confirmations.
- **[APPLIES] Pre-mortem** — 12 failure modes in §3 (above 5-10 floor).
- **[APPLIES] Multi-direction trace** — §6 per D-decision.
- **[APPLIES] Backward compat** — no breaking changes. All existing tests run unchanged; markers are additive metadata.
- **[APPLIES] Doc updates** — closure narrative to CLAUDE.md + parent + subdir complete-plan.md + to_be_checked.md + 2 memory files. 5-surface closure (no twin-filename violation — `p0_s7_privacy_critical_*` filename pattern is the disambiguator).

**Total: 10 APPLIES + 1 N/A (privacy, with rationale).** Matches P0.S5 + P0.S6 canonical shape.

---

## §9. Banked dispositions for Plan v1 review

- **Sub-pattern A (`### Phase-0-catches-wrong-premise`) doctrine: STAYS at 6 instances.** P0.S7 was partial-truth ON-TARGET premise; same shape as P0.S6 (privilege half closed, intent+fallback+handler open).
- **`### Phase-0-granular-decomposition-enables-accurate-estimates` doctrine: STAYS at 8 supporting** (closure-conditional bump to 9 if P0.S7 lands ON-TARGET under re-baselined methodology).
- **`### Spec-first review cycle`: 33 → 34 at Phase 0 close** (per locked +1-per-artifact convention from P0.S6 closure adjudication).
- **Strict-industry-standard mode: 23 → 24 consecutive applications + 7 closures** (in-flight to 8 at P0.S7 close).
- **Deferred-canary strategy: 6th → 7th application in-flight.**
- **Twin-filename pitfall: 4th + 1 = 5th successful prevention** at Phase 0 audit drafting (filename `p0_s7_privacy_critical_*.md` disambiguates against all earlier-closed P0.S7 family artifacts).
- **`### Phase-0-catches-scope-expansion` informal observation: stays at 2 instances** (P0.S7 Phase 0 doesn't expand scope; the structural drift protection in D4 is a partial-truth refinement, not a scope expansion in the same sense as P0.S6's _TOOL_HANDLERS surface).
- **Convention-drift-on-discipline-counts: 1 instance, applied at Phase 0** (count from 32 → 34 via 33 + Plan v1 = 34 per locked +1-per-artifact convention).

---

## §10. Banked open questions for auditor (3)

**Q1.** D3 dual-step vs single-step in fast.yml: §3.2 lists two options. Architect's lean: SINGLE-step approach — modify default pytest invocation to exclude `privacy_critical` AND add second dedicated step. Cleaner CI output + each test runs once. If auditor disagrees, Plan v1 adjudicates the alternative.

**Q2.** D3 fail-on-skip mechanism: §3.3 lists three options (--no-skips plugin, custom conftest hook, post-pytest grep). Architect's lean: post-pytest grep is simplest + doesn't add a runtime dependency. Lock at Plan v1 OR auditor adjudicates a different mechanism.

**Q3.** D2 marker convention (class-level vs module-level vs function-level): §3.6 + §4 enumerate. Architect's lean: class-level for 4 named classes, module-level (`pytestmark`) for single-purpose files, function-level for standalone tests in mixed files. If auditor prefers a different convention (e.g., function-level everywhere for explicit-greppability), Plan v1 absorbs.

---

**End of Phase 0 audit.** Ready to forward to auditor for Phase 0 review → Plan v1.
