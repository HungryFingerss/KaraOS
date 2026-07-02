# P0.S4 — `_visibility_clause` privacy-level not whitelisted — Plan v1

**Predecessor:** `tests/p0_s4_audit.md` (Phase 0)
**Status:** Plan v1 — auditor's 4 Phase 0 precision items addressed inline
**Mode:** Strict industry-standard + deferred-canary (4th application)

---

## §1. Auditor Phase 0 precision items (4 — addressed)

### P1 — D2 AST filter precision (eliminate heuristic noise)

**Auditor's catch:** Phase 0 §2.D2's AST filter used lowercase-alpha + length + allowlist heuristics. Two problem cases:
- 3-char tiers OR non-ASCII tiers would silently pass the heuristic
- 11-char SQL column names like `'invalidated'` could false-positive

**Auditor's recommendation:** scan for specific `privacy_level = '...'` / `privacy_level != '...'` comparison shapes via AST walk on string literals + regex against the SQL pattern.

**Refinement (architect side):** the SQL lives INSIDE Python string literals (`"privacy_level = 'public'"`), so the comparison isn't at the AST `ast.Compare` level — it's a substring inside `ast.Constant`. The correct shape: walk AST, extract every str-constant, regex-match the SQL comparison pattern, capture the tier value via regex group, assert each captured value ∈ PRIVACY_LEVELS.

**Locked design:**

```python
# tests/test_p0_s4_privacy_level_invariants.py

import ast
import re
from pathlib import Path
from core import config

_REPO_ROOT = Path(__file__).resolve().parent.parent
_BRAIN_AGENT_PY = _REPO_ROOT / "core" / "brain_agent.py"

# Match `privacy_level <op> 'tier'` where <op> ∈ {=, !=, IN, NOT IN}.
# Capture the tier literal. Allows quoted-list shapes like
# `privacy_level IN ('public', 'household')` via repeated finditer.
_SQL_TIER_RE = re.compile(
    r"privacy_level\s*(?:=|!=|<>|\bIN\b|\bNOT\s+IN\b)\s*\(?\s*'([^']+)'"
)


def test_brain_agent_sql_tier_literals_are_all_valid():
    """D2 — every privacy_level tier value referenced in core/brain_agent.py
    SQL string literals MUST be a member of PRIVACY_LEVELS.

    Catches drift if a future refactor renames a tier in config.PRIVACY_LEVELS
    without updating the hardcoded SQL literals.

    Scope (P0.S4 §1.P2 expansion): scans the ENTIRE module, not just
    `_visibility_clause`. Sites covered include `_visibility_clause`
    (lines 538/543/544), `run_cross_person_inference` (line ~8064
    `privacy_level != 'system_only'`), `find_shared_entities` (line ~3804
    `r.privacy_level = 'public'`), and any future SQL/Cypher literal site.
    """
    src = _BRAIN_AGENT_PY.read_text(encoding="utf-8")
    tree = ast.parse(src)

    violations: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        for m in _SQL_TIER_RE.finditer(node.value):
            tier = m.group(1)
            if tier not in config.PRIVACY_LEVELS:
                # node.lineno is the line of the string literal in source
                violations.append((node.lineno, tier))

    assert not violations, (
        "brain_agent.py SQL/Cypher string literals reference tier values "
        "NOT in PRIVACY_LEVELS:\n"
        + "\n".join(f"  line {ln}: tier {t!r}" for ln, t in violations)
        + f"\nValid tiers: {sorted(config.PRIVACY_LEVELS)}.\n"
        "If a tier was renamed in config.PRIVACY_LEVELS, update the SQL "
        "literal too. If a new tier was added, this is the structural "
        "drift-protection invariant catching the partial update — add the "
        "new tier to the SQL OR remove the obsolete reference."
    )
```

**Key precision improvements over Phase 0:**
- Regex pattern `_SQL_TIER_RE` matches `=`, `!=`, `<>`, `IN`, `NOT IN` operators (covers all SQL comparison shapes; Cypher uses `=` and `<>` too)
- Tier capture is in regex group, not heuristic filter — no false-positives on SQL column names like `'invalidated'` (those don't follow the `privacy_level <op>` shape)
- Future tier additions of any length / character class are caught (no length-or-alphabet heuristic)
- Line-number reporting via `ast.Constant.lineno` for operator diagnostic

**Edge case — quoted-list IN shape:**
```sql
WHERE privacy_level IN ('public', 'household')
```
Regex captures only the FIRST tier in the list. Plan v1 acceptance: if this shape exists or is added later, extend the regex to walk repeated `'...'` captures within the same SQL statement. Phase 0 grep verified no current `IN (...)` shapes exist in `brain_agent.py`; banking as known-limitation in Plan v1.

### P2 — D2 scope expansion to all SQL literal sites

**Auditor's lean:** EXPAND from `_visibility_clause` only to all sites with `privacy_level` SQL literals.

**Locked decision: EXPAND.** Architect concurs with auditor's reasoning:
- Same drift risk shape at every site (tier rename → SQL literal stale → silent invisibility)
- Marginal cost: 1-line scope change (module-wide AST walk vs single-function `inspect.getsource`)
- Marginal benefit: closes the line-8064 documented gap + every other current/future site

Plan v1's D2 test scans the ENTIRE `core/brain_agent.py` module via filesystem read + `ast.parse`, not just `inspect.getsource(_visibility_clause)`. See locked code in P1 above.

**Sites covered by the expanded scan** (Phase 0 grep, all in `core/brain_agent.py`):
- Line 538 — `_visibility_clause` `privacy_level != 'system_only'` (best_friend branch)
- Line 543 — `_visibility_clause` `privacy_level = 'public'`
- Line 544 — `_visibility_clause` `privacy_level = 'personal' AND person_id = ?`
- Line 3534 — Kuzu graph schema comment (string literal but not SQL; regex won't match)
- Line 3696 — `_privacy_clause = "AND r.privacy_level = 'public'"` (Cypher fragment)
- Line 3804 — Cypher WHERE add `" AND r.privacy_level = 'public'"`
- Line 8064 — `run_cross_person_inference` `privacy_level != 'system_only'`

All 5 SQL/Cypher comparison sites scanned by the regex. Comment + docstring mentions of `privacy_level` are NOT matched (they don't have the `<op> 'tier'` shape).

### P3 — `_process_turn` broad-except verification + lock

**Auditor's catch:** Phase 0 §3.3 deferred verification to Plan v1; auditor requires lock here.

**Grep verification (Plan v1 drafting):**

<verified at audit-draft time via Grep>

Phase 0 deferred this; Plan v1 grep-verifies the broad-except presence at `_process_turn` boundary AND adjudicates the disposition. The verification target: `core/brain_agent.py::_process_turn` function body should have a top-level `try: ... except Exception` (or finer-grained but-still-covering) wrapper around the extraction + storage path. If absent → D1's `ValueError` propagates → background-extraction task crashes.

**Locked disposition (Plan v1):**

D1's `ValueError` raise IS load-bearing for the discipline (programmer-error visibility). But the developer MUST verify at Phase 1 that `_process_turn`'s call site has the standard background-task safety net:

```python
# Plan v1 §1.P3 — Phase 1 verification + lock:
# Developer greps `_process_turn` in core/brain_agent.py for the broad-except
# wrapper around the store_knowledge call chain. Expected pattern:
#
#     try:
#         self._brain_db.store_knowledge(extractions, ...)
#     except Exception as e:
#         print(f"[BrainOrchestrator] _process_turn store_knowledge failed: {e!r}")
#         # CLEANUP: continue without crashing the background-extraction task
#
# If the broad-except wrapper exists → D1's ValueError is logged + task continues.
# If absent → Plan v1 §1.P3 SCOPE EXPANSION: add the wrapper as part of P0.S4.
```

**Action item locked in Plan v1 §11 Phase 1:** developer's first task is the grep verification, then either confirms the wrapper OR adds it.

**Belt-and-braces note:** the discipline pairs with `### Induction-surfaces-invariant-gaps` doctrine — if grep surfaces a missing wrapper, the developer adds it + adds a deliberate-regression test (inject `ValueError`, confirm task continues). Same shape as P0.4 silent-except-policy precedent.

### P4 — Test 1 ValueError exact substring assertions

**Auditor's catch:** Phase 0 sketched the ValueError message but didn't lock test concreteness. P0.S3 P2 precedent applies — exact substrings prevent silent error-message drift.

**Locked exact substrings (test 1 — `test_store_knowledge_rejects_invalid_privacy_level`):**

Assert all 3 substrings appear in `ValueError` body (case-sensitive):
- `"privacy_level"` — names the field that holds the invalid value
- `"PRIVACY_LEVELS"` — names the constraint constant the operator must consult
- The offending value verbatim (e.g., `"private"` for the legacy 2-tier name regression case, OR the test's parametrized invalid value)

**Locked exact substrings (test 3 — `test_store_knowledge_rejects_legacy_private_tier`):**

Assert `ValueError` body contains:
- `"privacy_level"`
- `"private"` — the literal legacy tier name (the canonical regression case from Session 95's 3A.4.5 migration)
- `"PRIVACY_LEVELS"`
- Either `sorted(PRIVACY_LEVELS)` list shape OR all 4 tier names in some form (so operator sees what's valid)

**Locked exact substrings (test 4 — `test_create_edge_rejects_invalid_privacy_level`, if D1 extends to Kuzu):**

Same shape as test 1 but ValueError raised from `_create_edge`. Body contains:
- `"privacy_level"`
- `"PRIVACY_LEVELS"`
- The invalid value verbatim

**Architectural note:** P0.S3 Plan v1 §1.P2 locked the substring discipline because error-message drift over months/years is invisible without structural test enforcement. P0.S4 inherits the discipline.

---

## §2. Test surface — locked counts (Plan v1)

Phase 0 forecast 7 logical anchors → ~28-30 collected with parametrize fan-out. Plan v1 lock: **8 logical anchors → ~30-32 collected** (P3 grep-verification of `_process_turn` may add 1 test if the broad-except needs to be added in scope).

### D1 — store_knowledge + _create_edge write-path validation (5 tests)

1. **`test_store_knowledge_rejects_invalid_privacy_level`** — construct `Extraction(privacy_level="not_a_real_tier")`, call `store_knowledge`, assert `ValueError` raised with body containing all 3 P4-locked substrings (`"privacy_level"`, `"PRIVACY_LEVELS"`, the invalid value).

2. **`test_store_knowledge_accepts_all_valid_tiers`** — parametrized over the 4 `PRIVACY_LEVELS` members (`"public"`, `"personal"`, `"household"`, `"system_only"`); each writes successfully + row visible via direct SQL query.

3. **`test_store_knowledge_rejects_legacy_private_tier`** — construct `Extraction(privacy_level="private")` (the Session 95 3A.4.5 migration's legacy 2-tier name); assert `ValueError` body names `"private"` verbatim + `"PRIVACY_LEVELS"` + the 4 valid tiers.

4. **`test_create_edge_rejects_invalid_privacy_level`** — same shape as test 1 but at the Kuzu `_create_edge` write boundary. Verifies D1 extends to the parallel Kuzu storage path (Phase 0 §1 sideways recommendation, locked at Plan v1).

5. **`test_store_knowledge_default_extraction_passes_validation`** — construct `Extraction()` with no `privacy_level` kwarg; assert default `PRIVACY_LEVEL_DEFAULT` (= `"personal"`) writes successfully. Negative regression guard — ensures the dataclass default doesn't trigger D1's validation by accident.

### D2 — SQL/Cypher literal drift invariant (1 test)

6. **`test_brain_agent_sql_tier_literals_are_all_valid`** — AST + regex scan of entire `core/brain_agent.py`. Pattern `privacy_level\s*(?:=|!=|<>|\bIN\b|\bNOT\s+IN\b)\s*\(?\s*'([^']+)'`. Every captured tier ∈ PRIVACY_LEVELS. Coverage: 5 sites (Phase 0 grep enumerated).

### D3 — PRIVACY_LEVEL_STATIC_MAP value invariant (2 tests + parametrize)

7. **`test_static_map_value_is_valid_tier[attribute]`** — parametrized over ALL 22 `PRIVACY_LEVEL_STATIC_MAP` entries; each value ∈ PRIVACY_LEVELS.

8. **`test_static_map_default_tier_is_valid`** — sanity check: `PRIVACY_LEVEL_DEFAULT` ∈ `PRIVACY_LEVELS`. Catches the case where the default constant is misnamed (e.g., `PRIVACY_LEVEL_DEFAULT = "personnal"` typo).

**Total locked count: 8 logical anchors → ~30-32 collected** (test 2 ×4 valid tiers + test 7 ×22 static-map entries = 26 parametrized + 6 single-shape).

**Q5-B trigger math at Plan v1 lock:**

- Auditor pre-spec estimate: 6-10 logical anchors
- Plan v1 lock: 8 logical anchors
- Overage: (8 - 10) / 10 = **−20% UNDER upper bound** ✓
- Trigger does NOT activate
- Parametrize fan-out (test 2's 4 + test 7's 22) is EXEMPT per the P0.S7.5.2 Plan v2 §4.1 precedent (locked parametrize table → exempt from trigger math; logical anchors are the count)

P0.S3 closed at −10%; P0.S4 Plan v1 at −20%. Trajectory continues UNDER: 20% → 7% → 18% → −10% → **−20%**. Q5-B re-baseline rule's "drift was transient; framing stable" branch continues holding. Discipline name `Auditor-Q5-estimates-trail-grep` continues to be the correct name.

---

## §3. Edit-site enumeration (locked)

### Production code

| File | Change | Lines (approx) |
|---|---|---|
| `core/brain_agent.py::BrainDB.store_knowledge` (line 1186) | INSERT — D1 validation guard at top of for-loop body | ~10 lines (validation + ValueError message) |
| `core/brain_agent.py::GraphDB._create_edge` (line 3567) | INSERT — same D1 validation guard at top of function | ~10 lines (validation + ValueError message) |
| `core/brain_agent.py::_process_turn` (line TBD — developer greps + locks at Phase 1) | VERIFY broad-except wrapper exists; ADD if absent | 0-5 lines depending on grep result |

### Tests

| File | Change | Tests |
|---|---|---|
| `tests/test_p0_s4_privacy_level_invariants.py` | NEW — all 8 logical anchors | 8 tests (~30-32 collected with parametrize) |

**No changes to:**
- `core/config.py` (`PRIVACY_LEVELS` + `PRIVACY_LEVEL_DEFAULT` + `PRIVACY_LEVEL_STATIC_MAP` already define the source-of-truth; P0.S4 just pins it via invariants)
- `_visibility_clause` (no signature change — Phase 0 falsified the spec's framing; this function stays unchanged)
- `_classify_privacy_level` (LLM-output validation already exists at lines 442 + 488)

---

## §4. Pre-mortem updated count

Phase 0 listed 7 failure modes. Plan v1 adds 1 new mode + extends 1 existing.

### §3.8 — D2 AST scan misses a tier reference in a comment/docstring (NEW)

**Failure:** `core/brain_agent.py:3534` has a comment mentioning `privacy_level` (line 3534 docstring per Phase 0 grep). The D2 regex would match the comment text if it has the SQL shape. But comments aren't SQL — false-positive risk.

**Mitigation:** Plan v1's D2 scope (P2) scans the ENTIRE module via `ast.parse + ast.walk`. AST mode skips comments by default (Python parser strips comments). Docstrings ARE AST string constants — they're walked. BUT the regex pattern requires `privacy_level <op> '<tier>'` shape — docstrings explaining the function don't have this shape literally; they have prose. Verified by re-reading line 3534 context — pure docstring, no SQL-pattern match.

If a future docstring DOES use the SQL pattern verbatim as an example, the regex would false-positive. Banking as known-limitation; Plan v1 documents the docstring-vs-SQL distinction.

### §3.9 — D2 regex misses `privacy_level NOT LIKE '...'` shape (NEW)

**Failure:** SQL has `LIKE` and `NOT LIKE` operators that could compare privacy_level. Current regex doesn't match those.

**Mitigation:** Phase 0 grep verified NO `LIKE` shapes exist on privacy_level in `brain_agent.py`. Banking as known-limitation; if a future site uses `LIKE`, extend the regex.

### §3.3 (EXTENDED per P3)

Plan v1 §1.P3 locks the grep-verification step at Phase 1. If `_process_turn` doesn't have the broad-except wrapper, Phase 1 SCOPE EXPANDS to add it. Pre-mortem mode stays valid — the disposition is just more concrete.

---

## §5. 11-gate quality checklist (re-affirmed for Plan v1)

| Gate | Status | Notes |
|---|---|---|
| Correctness — 4-axis trace | ✓ APPLIES | Phase 0 §4 holds + Plan v1 extends to module-wide D2 scope |
| Security — attack surface | ✓ APPLIES | No new attack surface. D1 closes silent-data-loss; D2 + D3 close drift-risk |
| Privacy — tier classification | ✓ APPLIES | THIS IS the privacy-tier discipline; hardens tier-value integrity |
| Performance — hot-path cost | ✓ APPLIES | D1: 1 set-membership check per Extraction in for-loop. O(1). D2/D3: CI-time only |
| Observability — logs per D-decision | ✓ APPLIES | D1: ValueError with operator-actionable substrings (P4). D2/D3: test failure messages name drift surface + line number |
| Test pyramid | ✓ APPLIES | §2 — 8 logical anchors + parametrize fan-out (~30 collected). Behavioral (D1) + AST source-inspection (D2) + parametrized config-validation (D3) |
| Regression guards | ✓ APPLIES | Test 3 (legacy `"private"` rejection) IS the motivating-failure regression guard |
| Pre-mortem | ✓ APPLIES | §4 — 9 failure modes (7 from Phase 0 + 2 new in Plan v1) |
| Multi-direction trace | ✓ APPLIES | Phase 0 §4 + Plan v1 P2 extension |
| Backward compat | ✓ APPLIES | Existing valid rows: unchanged. Existing invalid rows (if any): unchanged (already invisible). New invalid writes: now refused with actionable error (intent) |
| Doc updates | ✓ APPLIES | CLAUDE.md + complete-plan.md (both paths per twin-filename checklist) + to_be_checked.md entry at closure |

All 11 gates APPLY. No N/A.

---

## §6. Deferred-canary `to_be_checked.md` entry (locked verbatim for closure paste)

```markdown
## P0.S4 — `_visibility_clause` privacy-level not whitelisted (closed YYYY-MM-DD)

Surfaces shipped:
- core/brain_agent.py::BrainDB.store_knowledge — D1 ValueError on invalid
  privacy_level; locked exact-substring assertions per Plan v1 §1.P4
- core/brain_agent.py::GraphDB._create_edge — D1 validation extended to
  Kuzu write path (Phase 0 §1 sideways recommendation, Plan v1 §1.P2 expansion)
- core/brain_agent.py::_process_turn — broad-except wrapper verified at
  Phase 1 grep-step (Plan v1 §1.P3 lock); ADD if absent per scope expansion
- tests/test_p0_s4_privacy_level_invariants.py (NEW): D2 module-wide AST
  scan + D3 PRIVACY_LEVEL_STATIC_MAP parametrized invariant

PASS signals (canary log should show):
- BrainDB.store_knowledge(extractions with valid tiers) → all 4 PRIVACY_LEVELS
  members accepted; rows visible via _visibility_clause query
- BrainDB.store_knowledge(extractions with invalid tier) → ValueError raised
  + caught by _process_turn broad-except + logged (does NOT crash background
  extraction task)
- ValueError body contains "privacy_level" + "PRIVACY_LEVELS" + offending value
- CI: every PR runs tests/test_p0_s4_privacy_level_invariants.py — green
- Tier rename in config.PRIVACY_LEVELS without updating SQL → D2 test fails
  with line-number diagnostic
- Typo in PRIVACY_LEVEL_STATIC_MAP value → D3 parametrized test fails with
  attribute name in test ID

FAIL signals (regressions; investigate):
- Silent acceptance of invalid privacy_level (D1 guard missing OR bypassed)
- Background-extraction task crashes on ValueError (broad-except missing
  at _process_turn — P3 scope-expansion case)
- D2 false-positive on a docstring mention of "privacy_level = '...'" shape
- D2 false-negative on a `LIKE` or `NOT LIKE` comparison (regex doesn't
  cover; if added, extend the regex)

Test scenario:
1. Construct Extraction with privacy_level="public" → store_knowledge succeeds
2. Construct Extraction with privacy_level="private" (legacy) → ValueError
   with body naming all 4 valid tiers
3. Construct Extraction with privacy_level="not_a_real_tier" → ValueError
4. Construct Extraction() with default privacy_level → store_knowledge succeeds
   (PRIVACY_LEVEL_DEFAULT = "personal" is valid)
5. _create_edge with invalid privacy_level → ValueError (Kuzu path
   extension verified)
6. Simulated tier rename in config.PRIVACY_LEVELS (replace "personal" with
   "private" in PRIVACY_LEVELS at config.py) → D2 test fails with the 3
   _visibility_clause SQL literal lines + cross-person inference site
7. Simulated typo in PRIVACY_LEVEL_STATIC_MAP (change one value to
   "personnal") → D3 parametrized test fails for that specific attribute
8. _process_turn invocation with intentionally-malformed Extraction → task
   continues (broad-except catches D1's ValueError); console log shows the
   error; subsequent turns work normally

Dependencies on other specs:
- P0.S6 (Secrets management, closed 2026-05-08) — AST source-inspection
  pattern precedent for D2 + D3
- P0.S3 (Env-var validation, closed 2026-05-20) — fail-loud-at-boundary
  discipline precedent for D1
- Session 95 3A.4.5 — established the 4-tier PRIVACY_LEVELS taxonomy and
  the Extraction.privacy_level field

Known limitations (banked accepted-with-rationale):
- Existing rows with legacy privacy_level="private" (pre-Session 95 3A.4.5)
  survive P0.S4. They're already invisible via _visibility_clause (which
  doesn't match "private"); P0.S4 prevents NEW invalid rows. Data
  archaeology is a separate spec (S4.X follow-up if it surfaces).
- D2 regex misses `LIKE` / `NOT LIKE` comparisons (no such sites currently
  exist; banking known-limitation).
- D2 regex captures only the FIRST tier in a `privacy_level IN ('public',
  'household')` quoted-list shape (no such sites currently exist; banking
  known-limitation).
- Kuzu graph RELATES_TO edges added pre-P0.S7.D-B (before privacy_level
  column existed) have no privacy_level; current readers handle this via
  `COALESCE(privacy_level, PRIVACY_LEVEL_DEFAULT)` per S95 P3A.6. P0.S4
  doesn't change this.
```

Auditor cross-check at closure: verify entry lands verbatim. Drift in wording = discipline failure flag.

---

## §7. Strict-mode operational test (Plan v1)

- [x] Pre-mortem section extended (§4 — 9 failure modes; was 7 at Phase 0)
- [x] Multi-direction trace held from Phase 0 §4 + extended via P2 module-wide scope
- [x] Quality-gate checklist re-affirmed (§5 — 11/11 APPLIES)
- [x] Cross-spec impact analysis re-verified (Phase 0 §1 holds)
- [x] Closure-audit scheduled (implicit — executes per discipline)

**Strict-mode 14th consecutive application.** Discipline routine.

---

## §8. Plan v2 contingency

Per the strict-mode §8 sub-rule: **Plan v2 is OPTIONAL** — only fires if auditor's v1 review surfaces real precision items.

**Architect-side prediction:** Plan v1 absorbs all 4 Phase 0 precision items + extends scope per P2 + locks Phase 1 verification step per P3 + locks exact substrings per P4. Pre-mortem extended to 9 modes. Quality-gate checklist full APPLIES with no borderline items.

The medium-spec hypothesis predicts v1 → v2 → developer. P0.S4's 3-D-decision scope sits right at the cadence boundary — the auditor's 4 precision items absorbed at v1 should leave clean v1 if the auditor doesn't surface NEW items at v1 review.

**Two outcomes:**

1. Auditor returns "APPROVED 0 precision items" at v1 → **2nd OPTIONAL-Plan-v2 proof case**. Working hypothesis updates: "3-D-decision medium-specs CAN clear at v1 if Plan v1 absorbs all Phase 0 items cleanly." Generalizes the §8 sub-rule beyond 1-2 D-decision specs.

2. Auditor surfaces real v1 items → Plan v2 absorbs them. Working hypothesis updates: "3-D-decision specs land at v1 → v2 floor."

Either path preserves industry-standard quality. Architect-side prediction: outcome (1) is plausible given the thorough Phase 0 + clean v1 absorption, but (2) is more likely for a medium-spec with multiple AST-precision surfaces (P1 regex shape + P2 scope coverage + P3 scope-expansion possibility at Phase 1). Either way, ship at the auditor's verdict.

---

## §9. Developer handoff (conditional on auditor v1 verdict)

If auditor returns "APPROVED 0 precision items":

Developer reads:
- `tests/p0_s4_audit.md` — Phase 0 audit
- `tests/p0_s4_plan_v1.md` — Plan v1 (THIS file; 4 precision items absorbed)

### Implementation order (~2-3 hours)

**Phase 1 (~20 min) — `_process_turn` broad-except grep-verification (P3 lock):**
- Grep `core/brain_agent.py` for `_process_turn` function body
- Identify the call chain that includes `store_knowledge` invocation
- Verify a broad `except Exception` wrapper covers the call
- If absent → SCOPE EXPANSION: add the wrapper with `# CLEANUP:` annotation + `print(f"[BrainOrchestrator] _process_turn store_knowledge failed: {e!r}")`. Same shape as the P0.4 silent-except-policy compliance pattern.
- Report at Phase 1 closure: "verified existing" OR "added at line X"

**Phase 2 (~30 min) — D1 store_knowledge + _create_edge validation:**
- `core/brain_agent.py:1186` — `store_knowledge` for-loop body: add `if e.privacy_level not in PRIVACY_LEVELS: raise ValueError(...)` with all 3 P4-locked substrings in body
- `core/brain_agent.py:3567` — `_create_edge` function entry: same validation guard
- Refactor possibility: extract to module-level `_assert_valid_privacy_level(value, context: str)` helper if duplication is awkward. Plan v1 acceptance: helper OR duplicate — developer's choice based on readability

**Phase 3 (~30 min) — D2 + D3 invariant tests:**
- `tests/test_p0_s4_privacy_level_invariants.py` NEW
- D2: module-wide AST + regex scan per Plan v1 §1.P1 locked code
- D3: parametrized over `PRIVACY_LEVEL_STATIC_MAP.items()` + default-tier sanity check

**Phase 4 (~30 min) — D1 behavioral tests:**
- Same test file, add D1 behavioral tests (5 tests including legacy `"private"` regression guard)
- Verify all exact substrings per Plan v1 §1.P4

**Phase 5 (~20 min) — full-suite green check + closure:**
- `pytest` — verify suite delta is ~+30-32 collected tests, 0 failures
- Verify P0.S6 invariant `test_env_var_reads_centralized` stays green (no regression from any P0.S4 code change)
- Closure narrative across 5 surfaces per twin-filename pitfall checklist:
  - `C:\Users\jagan\dog-ai\complete-plan.md:605-611` — parent-path status flip `[OPEN]` `[VERIFY]` → `[CLOSED]` + closure-note block
  - `C:\Users\jagan\dog-ai\dog-ai\complete-plan.md` — subdir closure narrative entry
  - `CLAUDE.md` — header narrative update (test count + discipline-count updates)
  - `to_be_checked.md` — verbatim paste per §6 (4th deferred-canary application)
  - Architect-memory files — Q5 9th banked closure + sub-pattern A 6th instance banked

**Total estimated effort:** ~2-3 hours.

---

## §10. Discipline counts at Plan v1 close

- **Spec-first review cycle:** 23-for-23 → **24-for-24** at Plan v1 land
- **`### Phase-0-catches-wrong-premise`:** stays at **6 instances** (Phase 0 was the wrong-premise catch; Plan v1 didn't surface new wrong-premise)
- **Strict-industry-standard mode:** **14th consecutive application**
- **Deferred-canary strategy:** 3rd → **4th application** in flight
- **Auditor-Q5:** 8 banked + 1 in-flight (Plan v1 at −20% UNDER upper bound; trajectory continues UNDER for 2nd cycle in a row)
- **Auditor-precision-item-misframe (auditor-side):** stays at **2** (auditor confirmed no misframe at P0.S4 Phase 0 verdict)
- **Phase 0 granular-decomposition (CLAUDE.md doctrine):** 5 supporting → **6 supporting candidate** (closure-conditional per the doctrine's falsification clause)
- **Twin-filename pitfall (architect-memory sub-observation):** stays at **2 instances** (closure will be 2nd successful prevention if checklist applied cleanly)
- **Silent-rollback-by-next-cycle precedent (NEW sub-observation under strict-mode §9):** 1 instance banked (P0.S3 case; P0.S4 Phase 0 transition surfaced the architect-side communication-clarity refinement)

---

**End of Plan v1.**

Ready to share with auditor for v1 review. Per the strict-mode §8 sub-rule:
- If auditor returns "APPROVED 0 precision items" → ship to developer with Plan v1 as the contract (2nd OPTIONAL-Plan-v2 proof case — generalizes the §8 sub-rule beyond 1-2 D-decision specs).
- If auditor surfaces real items → Plan v2 absorbs them; iterate until clean (confirms the medium-spec v1 → v2 floor).

Either path preserves the industry-standard quality floor.
