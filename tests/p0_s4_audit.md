# P0.S4 — `_visibility_clause` privacy-level not whitelisted — Phase 0 Audit

**Spec:** P0.S4 (complete-plan.md:605-611) — `_visibility_clause` privacy-level not whitelisted
**Track:** P0 — Security vulnerabilities (`[OPEN]` `[VERIFY]` V1)
**Mode:** Strict industry-standard (locked 2026-05-19) + deferred-canary (locked 2026-05-20)
**Predecessor closures:** P0.S3 (2026-05-20). Strict-mode now at 12 consecutive applications + 4 closures.

---

## 0. Pre-audit hypothesis vs grep evidence

**Pre-audit framing (spec text from complete-plan.md:608-610):**

> "Fix: `assert privacy_level in PRIVACY_LEVELS` before composing.
> Test: parametrized — every valid value passes; rogue values raise."

This wording implies `_visibility_clause` takes a `privacy_level` parameter and validates it before composing SQL. Pre-audit assumption: single-D-decision spec — add one assertion + parametrized test, done.

**Phase 0 grep-verified findings — PREMISE FALSIFIED:**

| Surface | File:Line | Current state | Falsification |
|---|---|---|---|
| `_visibility_clause` signature | `core/brain_agent.py:499-502` | `def _visibility_clause(requester_pid: str, best_friend_id: "str | None" = None) -> tuple[str, list]:` | **Does NOT take a `privacy_level` arg.** Spec's "assert privacy_level in PRIVACY_LEVELS before composing" cannot apply directly to this function — no privacy_level value to validate. |
| `_visibility_clause` body | `core/brain_agent.py:536-546` | Composes hardcoded SQL string literals: `'system_only'` (line 538), `'public'` (line 543), `'personal'` (line 544) | The tier values are CONSTANTS in the SQL, not parameters. The validation surface is "do these literals stay in sync with `PRIVACY_LEVELS`?" — a STRUCTURAL invariant, not a runtime assertion. |
| `PRIVACY_LEVELS` definition | `core/config.py:886-891` | `frozenset({"public", "personal", "household", "system_only"})` — 4 tiers locked at P0.S6 closure 2026-05-08 | Source of truth ✓ |
| `Extraction.privacy_level` default | `core/brain_agent.py:763` | `privacy_level: str = PRIVACY_LEVEL_DEFAULT` (= "personal") | Dataclass default fail-closed ✓; but **no validation that constructor-provided value is in PRIVACY_LEVELS** — caller can construct `Extraction(privacy_level="private")` (legacy 2-tier name) silently |
| `BrainDB.store_knowledge` write path | `core/brain_agent.py:1186-1220` | INSERT writes `e.privacy_level` verbatim to SQL (line 1205) — **no validation guard** | Real validation gap — malformed `privacy_level` enters the row → `_visibility_clause` SQL never matches it → silent invisibility |
| `_classify_privacy_level` LLM output validation | `core/brain_agent.py:442, 488` | `if level not in PRIVACY_LEVELS: return PRIVACY_LEVEL_DEFAULT` | LLM-classifier output IS validated ✓ — fail-closed to default on invalid LLM response |
| `PRIVACY_LEVEL_STATIC_MAP` values | `core/config.py:899-936` | 22 attribute → tier entries, hand-curated | **No structural test that all values ∈ PRIVACY_LEVELS.** Typo (e.g., "personnal") → invalid tier → classifier static-map path silently returns invalid value |
| Other consumers of privacy_level | `core/brain_agent.py:3567 (`_create_edge`), :3606 (Kuzu edge writer), :3649/3864 (rebuild paths), :4097 (RoutineAgent), :8064 (cross-person inference)` | Many call sites, all passing `privacy_level=` as keyword | Each is a potential rogue-value injection point if the value isn't a `PRIVACY_LEVELS` member |

**Sub-pattern A wrong-premise instance — 6th instance candidate.** The pre-audit framing assumed `_visibility_clause` had a different signature; Phase 0 grep falsifies the premise. Actual scope is broader than the spec implied.

Per the `### Phase-0-catches-wrong-premise` doctrine (CLAUDE.md, elevated at P0.S7.D-D with 5-instance threshold): "future instances continue to be banked under this doctrine's track record." This is the **6th instance** — bumps the doctrine's track record from 5 → 6.

**Banking the wrong-premise type:** the spec text was written when `_visibility_clause` had a different signature OR the author conflated "validate `privacy_level` value" (write-path concern) with "validate `_visibility_clause` inputs" (function signature concern). The two are different surfaces; the spec text named only one but Phase 0 surfaces both.

**Actual scope under the corrected premise:** P0.S4 is **NOT a single-D-decision spec.** It's a **3-D-decision spec** covering 3 distinct validation surfaces:

1. **D1** — Input validation at `store_knowledge` write boundary
2. **D2** — Structural invariant on `_visibility_clause` SQL literals (drift protection)
3. **D3** — Structural invariant on `PRIVACY_LEVEL_STATIC_MAP` values (drift protection)

This is a **medium spec** per the strict-mode §8 sub-rule hypothesis (3-5 D-decisions, single subsystem). Expected cadence: **v1 → v2 → developer** (NOT the OPTIONAL-Plan-v2 path that P0.S3 just validated for 1-2 D-decision specs).

---

## 1. Cross-spec impact analysis

### Upstream dependencies

- **P0.S6 (Secrets management, closed 2026-05-08)** — `test_secrets_invariants.py` is the structural-invariant precedent. Uses AST source-inspection for similar drift-protection patterns. P0.S4's D2 + D3 invariants follow the same shape.
- **P0.S3 (Env-var validation, closed 2026-05-20)** — establishes the "validate at the boundary, fail-loud on invalid" pattern (`_validate_together_api_key` raises RuntimeError on empty). P0.S4's D1 follows the same boundary-validation discipline.
- **`PRIVACY_LEVELS` + `PRIVACY_LEVEL_DEFAULT` + `PRIVACY_LEVEL_STATIC_MAP` at `core/config.py:886-936`** — source of truth, established at P0.S6 + Session 95. P0.S4 invariants pin these as the canonical reference; any future tier addition/rename MUST go through PRIVACY_LEVELS.

### Downstream dependents

- **All knowledge retrieval call sites** that read through `query_knowledge_for` or `semantic_search_knowledge` (10+ call sites per Phase 0 grep) — they depend on `_visibility_clause`'s SQL literals matching the privacy_level values stored in rows. P0.S4 closes the drift risk between write-side values and read-side literals.
- **Future tier additions** (e.g., a hypothetical `confidential` tier per Session 95 banked future work) — would require updating PRIVACY_LEVELS + `_visibility_clause` SQL + PRIVACY_LEVEL_STATIC_MAP in sync. P0.S4's structural invariants FAIL at CI on partial updates, preventing silent drift.

### Sideways (parallel code paths)

- **Kuzu edge `_create_edge`** at `brain_agent.py:3567` — writes `privacy_level` to Kuzu graph (separate storage). If P0.S4 validates `store_knowledge` but not `_create_edge`, the Kuzu path can still ingest invalid tiers. Scope decision in D1.
- **RoutineAgent + `store_temporal_fact`** hard-code `privacy_level="personal"` (sync agents). These are correct-by-construction since they emit a small closed set; no validation gap.
- **Cross-person inference query** at `brain_agent.py:8064` — reads `privacy_level != 'system_only'` SQL literal directly. If P0.S4 only covers `_visibility_clause`, this site is unguarded. Scope decision in D2.

### Lifecycle trace

- **T=0 (Extraction construction):** Caller (ExtractionAgent / RoutineAgent / handwritten code) constructs `Extraction(privacy_level=...)`. Dataclass default is `PRIVACY_LEVEL_DEFAULT` (fail-closed). **No validation today.**
- **T=1 (store_knowledge write):** `store_knowledge` writes `e.privacy_level` verbatim to SQL (line 1205). **No validation today** — P0.S4 D1 adds it here.
- **T=2 (visibility query):** Caller invokes `query_knowledge_for(requester_pid, best_friend_id)` → composes via `_visibility_clause` → SQL literals match against stored `privacy_level` column.
- **T=∞ (tier addition):** Future spec adds a new tier (e.g., `confidential`) to `PRIVACY_LEVELS`. P0.S4 D2 + D3 invariants fail at CI if `_visibility_clause` SQL literals AND/OR `PRIVACY_LEVEL_STATIC_MAP` values aren't updated in sync.

All 4 axes traced. No gaps.

---

## 2. D-decisions enumerated

### D1 — `store_knowledge` write-path validation (P0 CORRECTNESS)

**Question:** What happens when an `Extraction` carries an invalid `privacy_level` value (e.g., `"private"` legacy 2-tier name, or a typo like `"personnal"`)?

**Current behavior:** Silent write. The INSERT at `brain_agent.py:1205` writes the value verbatim. Downstream `_visibility_clause` SQL never matches the invalid value → fact is INVISIBLE to all readers → silent data loss.

**Locked design:**

```python
# core/brain_agent.py::BrainDB.store_knowledge (line 1186)

def store_knowledge(
    self,
    extractions: list[Extraction],
    turn_id: int,
    person_id: str | None,
    agent: str,
) -> int:
    now = time.time()
    count = 0
    for e in extractions:
        # P0.S4 D1 — fail-loud on invalid privacy_level. Rogue values would
        # write rows that `_visibility_clause` can never match, causing silent
        # data loss. Better to refuse the write + surface a programmer error
        # than to lose the fact silently. Per the strict-mode "fail at the
        # boundary, surface programmer errors" discipline (P0.S3 precedent).
        if e.privacy_level not in PRIVACY_LEVELS:
            raise ValueError(
                f"[BrainDB.store_knowledge] Extraction has invalid "
                f"privacy_level={e.privacy_level!r} (entity={e.entity!r}, "
                f"attribute={e.attribute!r}). Must be one of: "
                f"{sorted(PRIVACY_LEVELS)}. Fix the caller's Extraction "
                f"construction or use PRIVACY_LEVEL_DEFAULT."
            )
        valid_until = _valid_until(e.is_temporal, e.valid_for_hours, now)
        self._conn.execute(
            """INSERT INTO knowledge ...""",
            (..., e.privacy_level),
        )
        ...
```

**Why fail-loud (raise) not fail-closed (default-to-personal):**

The classifier-output path at `_classify_privacy_level` ALREADY fails closed on invalid LLM output (returns `PRIVACY_LEVEL_DEFAULT`). The remaining invalid-value path is **programmer error** — handwritten Extraction with a typo. Programmer errors should fail loud at the closest boundary to the bug; silent fail-closed would mask the typo and create a debugging nightmare months later (every fact with the typo'd tier is invisible; nobody knows why).

**Scope decision — Kuzu `_create_edge` at line 3567:**

Plan v1 will decide whether D1 extends to the Kuzu write path. Phase 0 recommendation: YES — extend the same validation to `_create_edge` (single shared helper or duplicate the assertion). Rationale: same risk class, same severity, trivial cost.

**Edit sites:**
- `core/brain_agent.py:1186` — add validation at top of for-loop body
- `core/brain_agent.py:3567` — same validation at `_create_edge` (Plan v1 will lock module-level helper vs duplicate)

**Invariants established:**
- All `privacy_level` values written to `knowledge` table OR Kuzu RELATES_TO edges are members of `PRIVACY_LEVELS`
- Invalid values raise `ValueError` at the boundary (programmer-error visibility)

**Invariants preserved:**
- Dataclass default (`PRIVACY_LEVEL_DEFAULT`) handles the forget-to-classify case fail-closed
- LLM-classifier output validation at line 442 + 488 stays intact
- Sync agent hard-coded tiers (`"personal"`, `"public"`) — all valid PRIVACY_LEVELS members; pass through cleanly

---

### D2 — `_visibility_clause` SQL-literal drift invariant (DRIFT PROTECTION)

**Question:** What guards against `_visibility_clause` SQL literals drifting from `PRIVACY_LEVELS` config?

**Current behavior:** No structural test. A future refactor that renames `'personal'` to `'private'` in PRIVACY_LEVELS (or vice versa) would silently break `_visibility_clause` — the SQL would never match real stored values, every personal fact would become invisible.

**Locked design:** AST source-inspection test that extracts every `'X'` string literal from `_visibility_clause`'s function body, asserts each one (after filtering for SQL-tier-keyword context) is a member of `PRIVACY_LEVELS`.

```python
# tests/test_p0_s4_privacy_level_invariants.py

import ast
import inspect
from core import config
from core.brain_agent import _visibility_clause

def test_visibility_clause_sql_literals_are_all_valid_tiers():
    """D2 — every privacy-tier string literal in `_visibility_clause`
    MUST be a member of PRIVACY_LEVELS. Catches drift if a future refactor
    renames a tier in config.PRIVACY_LEVELS without updating the SQL.
    """
    src = inspect.getsource(_visibility_clause)
    tree = ast.parse(src)
    # Extract every str-constant referenced in a comparison context
    # adjacent to "privacy_level" — look for `privacy_level = '...'` or
    # `privacy_level != '...'` patterns.
    string_literals = [
        n.value for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
    ]
    # Filter for the tier-literal pattern (4-12 char lowercase ASCII)
    tier_candidates = [
        s for s in string_literals
        if 4 <= len(s) <= 20 and s.replace("_", "").isalpha() and s.islower()
        and s not in {"AND", "OR"}  # SQL keywords (defensive — none expected lowercase)
    ]
    # Every candidate that LOOKS like a tier MUST be in PRIVACY_LEVELS
    for s in tier_candidates:
        # Allow English words that aren't tiers (e.g., "person_id" column refs).
        # The check is: if the literal matches a tier-keyword shape AND ends
        # with the tier convention (no underscore-bracketed identifiers),
        # it must be in PRIVACY_LEVELS.
        if s in {"person_id", "entity"}:  # SQL column names, not tier values
            continue
        assert s in config.PRIVACY_LEVELS, (
            f"_visibility_clause SQL literal {s!r} is NOT in PRIVACY_LEVELS "
            f"({sorted(config.PRIVACY_LEVELS)}). This is a drift between "
            f"the function's hardcoded SQL and config.PRIVACY_LEVELS — if a "
            f"tier was renamed in config, update the SQL literal too."
        )
```

**Edit sites:**
- `tests/test_p0_s4_privacy_level_invariants.py` — NEW (D2 invariant tests; D3 in same file)

**Invariants established:**
- `_visibility_clause` SQL literals stay in sync with `PRIVACY_LEVELS`
- CI fails on partial-update tier renames

**Invariants NOT touched:**
- The SQL literals themselves stay hardcoded (no runtime templating — performance + readability win)
- The function signature stays unchanged

---

### D3 — `PRIVACY_LEVEL_STATIC_MAP` values invariant (DRIFT PROTECTION)

**Question:** What guards against `PRIVACY_LEVEL_STATIC_MAP` values drifting from `PRIVACY_LEVELS` config?

**Current behavior:** No structural test. A typo in a static-map value (e.g., `"personnal"` instead of `"personal"`) would silently flow through `_classify_privacy_level`'s static-map fast path → `Extraction.privacy_level = "personnal"` → `store_knowledge` writes invalid row → `_visibility_clause` never matches → fact invisible.

**Note interaction with D1:** if D1 ships, the typo would be caught by `store_knowledge`'s ValueError at runtime. But the typo would still flow through the static-map and only surface at first storage attempt. **D3 catches it at config-load time via CI**, before any storage attempt.

**Locked design:** parametrized test over all `PRIVACY_LEVEL_STATIC_MAP` entries.

```python
# tests/test_p0_s4_privacy_level_invariants.py (continued)

import pytest
from core import config

@pytest.mark.parametrize(
    "attribute,tier",
    list(config.PRIVACY_LEVEL_STATIC_MAP.items()),
    ids=lambda x: x if isinstance(x, str) else None,
)
def test_static_map_value_is_valid_tier(attribute, tier):
    """D3 — every value in PRIVACY_LEVEL_STATIC_MAP MUST be a member of
    PRIVACY_LEVELS. Catches typos at config-load time before any
    storage attempt.
    """
    assert tier in config.PRIVACY_LEVELS, (
        f"PRIVACY_LEVEL_STATIC_MAP[{attribute!r}] = {tier!r} is NOT in "
        f"PRIVACY_LEVELS ({sorted(config.PRIVACY_LEVELS)}). Typo or "
        f"missing tier addition? Fix the static map OR add the tier to "
        f"PRIVACY_LEVELS."
    )

def test_static_map_default_tier_is_valid():
    """D3 sanity — PRIVACY_LEVEL_DEFAULT itself is in PRIVACY_LEVELS."""
    assert config.PRIVACY_LEVEL_DEFAULT in config.PRIVACY_LEVELS
```

**Edit sites:**
- Same file as D2 tests (`tests/test_p0_s4_privacy_level_invariants.py`)

**Invariants established:**
- All static-map values are valid PRIVACY_LEVELS members
- `PRIVACY_LEVEL_DEFAULT` constant itself is a valid PRIVACY_LEVELS member (catches the case where the default is misnamed)

---

### D4 — Test surface

**Locked test list (Plan v1 will refine; Phase 0 forecasts):**

**D1 tests (4 tests):**
1. `test_store_knowledge_rejects_invalid_privacy_level` — construct `Extraction(privacy_level="invalid")`, call `store_knowledge`, assert `ValueError` with message naming the var + valid tiers.
2. `test_store_knowledge_accepts_all_valid_tiers` — parametrized over the 4 `PRIVACY_LEVELS` members; each writes successfully.
3. `test_store_knowledge_rejects_legacy_private_tier` — specific regression guard against `privacy_level="private"` (2-tier legacy name).
4. `test_create_edge_rejects_invalid_privacy_level` — same validation extends to Kuzu `_create_edge`.

**D2 tests (1 test):**
5. `test_visibility_clause_sql_literals_are_all_valid_tiers` — AST source-inspection.

**D3 tests (2 tests + parametrize fan-out):**
6. `test_static_map_value_is_valid_tier[attr]` — parametrized over 22 static-map entries.
7. `test_static_map_default_tier_is_valid` — sanity check on `PRIVACY_LEVEL_DEFAULT`.

**Forecast:** **7 logical anchors with parametrize fan-out** (test 2 ×4 valid tiers + test 6 ×22 static-map entries) = ~30 collected tests. Phase 0 logical-anchor estimate: **7-8 tests**; collected: ~28-30 with parametrize fan-out.

---

## 3. Pre-mortem — failure modes

Per strict-mode §1. Enumerated 7 failure modes (above the 5-10 floor).

### §3.1 — Existing rows with invalid privacy_level pre-P0.S4

**Failure:** Production DBs may have rows with legacy `"private"` tier values (from before Session 95 3A.4.5 migration). After P0.S4 D1, new writes are validated, but EXISTING rows with `"private"` are still in the table — invisible via `_visibility_clause` (which only matches `'public'`, `'personal'`, `'system_only'`).

**Mitigation:** Out of scope for P0.S4 (data migration vs validation surface — different specs). The migration question was settled at Session 95 3A.4.5: legacy `private` rows were re-classified at agent layer; the schema column kept the old name. If any `'private'` rows survived, they're already invisible (no read path matches them). P0.S4 prevents NEW invalid rows; data archaeology is a different spec (S4.X follow-up if it surfaces).

**Banking as known-limitation in Plan v1.**

### §3.2 — Sync agent constructs Extraction with wrong tier

**Failure:** RoutineAgent / `store_temporal_fact` hard-code `privacy_level="personal"`. Future sync agent could hard-code `privacy_level="public"` for an attribute that should be personal (silent privacy leak).

**Mitigation:** Out of scope for P0.S4 — that's an agent-design correctness question, not a validation surface. D1 catches structurally-invalid values (`"private"`, typos); semantic correctness (`"personal"` vs `"public"` for a given attribute) is an agent-quality concern.

### §3.3 — D1 ValueError crashes pipeline during conversation

**Failure:** `store_knowledge` runs inside `_process_turn` which runs in the background-extraction task. A `ValueError` from D1 propagates → background task crashes → orchestrator's notify-loop hits the exception.

**Mitigation:** Background-extraction tasks already have broad exception handling at the orchestrator level (per CLAUDE.md observability convention — log + continue, don't crash the loop). D1's `ValueError` will be logged with full traceback; the offending Extraction will be skipped. The user's conversation continues; the developer sees the error in logs at next session review.

**Verify in Plan v1:** confirm `_process_turn` actually has the broad except. If not, add one defensively (this is P0.4 silent-except-policy adjacent territory).

### §3.4 — D2 AST test false-positives on non-tier string literals

**Failure:** `_visibility_clause` contains other string literals (e.g., `"AND"`, `"person_id"`) that aren't privacy tiers but match the heuristic. D2 test's tier-filter logic could false-positive.

**Mitigation:** D2 test's filter narrows to lowercase ASCII strings with tier-like length AND explicitly allowlists known non-tier literals (`{"person_id", "entity"}`). Plan v1 will refine the filter regex if needed.

### §3.5 — D3 parametrize generates ~22 individual test IDs (CI noise)

**Failure:** Parametrized test 6 generates ~22 test IDs in pytest output. CI logs become noisier.

**Mitigation:** Use the `ids=` parameter to label each test by attribute name (already in the spec). CI output is human-readable. This is the same shape as P0.S6's parametrized invariant tests; precedent set.

### §3.6 — PRIVACY_LEVELS frozenset is mutated at test time

**Failure:** A test monkeypatches `config.PRIVACY_LEVELS` (e.g., to test rejection of an "ALMOST_VALID" tier). Other tests see the mutated frozenset → cross-test pollution.

**Mitigation:** `PRIVACY_LEVELS` is a frozenset (immutable). Monkeypatching `config.PRIVACY_LEVELS = {...}` replaces the module attr but the original frozenset is preserved in any code that already imported it. `monkeypatch.setattr` auto-restores at test end. No pollution risk.

### §3.7 — Future tier addition breaks D2 + D3 simultaneously

**Failure:** Future spec adds a `"confidential"` tier to `PRIVACY_LEVELS`. D2 (SQL literals) AND D3 (static map values) BOTH fail because neither was updated.

**Mitigation:** This is the INTENDED behavior — D2 + D3 are designed to fail in this case. Future spec MUST update `_visibility_clause` SQL + `PRIVACY_LEVEL_STATIC_MAP` in the same PR as the tier addition. CI failure is the discipline anchor.

---

## 4. Multi-direction invariant trace

### Forward

- **Knowledge retrieval consumers** (`query_knowledge_for`, `semantic_search_knowledge`, `get_active_knowledge`, `run_cross_person_inference`) — depend on `_visibility_clause` SQL literals matching stored values. P0.S4 D2 pins the literals.
- **Future tier additions** — must update PRIVACY_LEVELS + `_visibility_clause` SQL + STATIC_MAP atomically. D2 + D3 enforce.

### Backward

- **`Extraction` construction sites** (ExtractionAgent classifier path, RoutineAgent hard-codes, store_temporal_fact, fan-out at `_fan_out_to_participants`, RetroScan, etc.) — D1 catches structural validity at the write boundary. Each construction site has its own correctness responsibility; D1 is the safety net.
- **LLM classifier output validation** at `brain_agent.py:442 + 488` — already validates; preserved.

### Sideways

- **Kuzu `_create_edge`** — parallel write path with own privacy_level column. D1 extends to this path.
- **Cross-person inference at `:8064`** — reads `privacy_level != 'system_only'` SQL literal directly. **Potential D2 expansion** — Plan v1 will decide whether D2 invariant scans ONLY `_visibility_clause` OR all functions that contain `'privacy_level'` SQL literals. Phase 0 recommendation: ONLY `_visibility_clause` (single-function scope is cleaner; the other site is one literal, low drift risk).

### Lifecycle

- **T=0 (config load):** `PRIVACY_LEVELS` + `PRIVACY_LEVEL_STATIC_MAP` loaded. D3 invariant runs at CI.
- **T=1 (Extraction construction):** Dataclass default or explicit value. Caller responsibility.
- **T=2 (store_knowledge write):** D1 validation runs. Invalid → ValueError.
- **T=3 (visibility query):** `_visibility_clause` composes SQL. D2 invariant pinned at CI.
- **T=∞ (future tier add):** PRIVACY_LEVELS update fails D2 + D3 until SQL + STATIC_MAP are updated in sync.

All 4 axes traced. No gaps.

---

## 5. 11-gate quality checklist

| Gate | Status | Notes |
|---|---|---|
| Correctness — 4-axis trace | ✓ APPLIES | §4 |
| Security — attack surface | ✓ APPLIES | No new attack surface. D1 closes a silent-data-loss vector; D2 + D3 close drift-risk vectors. Both shrink the failure surface. |
| Privacy — tier classification | ✓ APPLIES | This IS the privacy-tier discipline. P0.S4 hardens the tier-value integrity. |
| Performance — hot-path cost | ✓ APPLIES | D1: 1 set-membership check per Extraction in `store_knowledge` for-loop. O(1). Negligible. D2/D3: CI-time only. |
| Observability — logs per D-decision | ✓ APPLIES | D1: ValueError message names the offending tier + entity + attribute + valid tiers (operator-actionable). D2/D3: test failure messages name the drift surface. |
| Test pyramid | ✓ APPLIES | §2.D4 — 7 logical anchors with parametrize fan-out → ~28-30 collected. Mix of behavioral (D1) + AST source-inspection (D2) + parametrized config-validation (D3). |
| Regression guards | ✓ APPLIES | D1 test 3 (legacy `"private"` rejection) IS the motivating-failure regression guard. |
| Pre-mortem | ✓ APPLIES | §3 — 7 failure modes |
| Multi-direction trace | ✓ APPLIES | §4 |
| Backward compat | ✓ APPLIES | Existing rows with valid tiers: unchanged. Existing rows with invalid tiers (if any): unchanged (already invisible). New writes with invalid tiers: now refused with actionable error (intent). No migration path needed — invalid writes were already silently broken. |
| Doc updates | ✓ APPLIES | CLAUDE.md Session entry + complete-plan.md P0.S4 status flip + to_be_checked.md entry at closure. |

All 11 gates APPLY. No N/A.

---

## 6. Deferred-canary `to_be_checked.md` plan

Per the deferred-canary strategy locked 2026-05-20: no live canary fires for P0.S4. At closure, an entry is added to `c:\Users\jagan\dog-ai\to_be_checked.md` covering:

- **PASS signals:** ValueError on invalid privacy_level write; clean writes for all 4 valid tiers; CI structural invariants (D2 + D3) pass on every PR.
- **FAIL signals:** silent acceptance of invalid privacy_level; new tier added to PRIVACY_LEVELS without updating `_visibility_clause` SQL or PRIVACY_LEVEL_STATIC_MAP (CI catches).
- **Test scenario:** 4-step sequence covering D1 happy path + D1 invalid rejection + D2 false-rename simulation + D3 false-tier simulation.

Plan v1 will lock the entry verbatim per the discipline.

---

## 7. Auditor-Q5 trigger watch

Per memory file `feedback_auditor_q5_estimates_trail_grep.md`: **P0.S4 is the 9th in-flight projection.** Following P0.S3's trajectory reversal (−10% UNDER upper bound), the 5-cycle trajectory was 20% → 7% → 18% → −10%. P0.S4's actual will determine the 6th-cycle reading.

- **Phase 0 forecast:** 7 logical anchors with parametrize fan-out → ~28-30 collected
- **Architect's expected auditor range:** 5-10 logical anchors (parametrize fan-out is exempt from logical-anchor count per Plan v2 §4.1 P0.S7.5.2 precedent)
- **Likely overage at Plan v1 lock:** within mid-range tolerance — Phase 0's 7-decomposition with named edit sites should produce ON-TARGET estimate per the `### Phase-0-granular-decomposition-enables-accurate-estimates` doctrine.

If actual closure is ≥30% over auditor upper bound non-DiD → Q5-B trigger activates per the locked rule. Phase 0 surface looks well-bounded; trigger should stay armed-but-not-fired.

## 8. Strict-mode operational test (Phase 0)

- [x] Pre-mortem section exists (§3 — 7 failure modes)
- [x] Multi-direction invariant trace exists (§4 — 4 axes)
- [x] Quality-gate checklist named (§5 — 11/11 APPLIES)
- [x] Cross-spec impact analysis exists (§1)
- [x] Closure-audit step scheduled (implicit — discipline floor)

All 5 strict-mode tests pass at Phase 0. **13th consecutive application** banked at Phase 0 land (12 prior + 1 here).

---

## 9. Discipline counts at Phase 0 close

- **Spec-first review cycle:** 22-for-22 → **23-for-23** at Phase 0 land
- **`### Phase-0-catches-wrong-premise`:** 5 → **6 instances** (6th instance: spec text's `_visibility_clause(privacy_level)` framing falsified by grep — function signature doesn't take `privacy_level`; actual scope is 3-D-decision validation+invariants surface). Per the doctrine's "future accumulation" clause, instances continue to bank without re-elevation.
- **Strict-industry-standard mode:** 12 applications + 4 closures → **13 consecutive applications** in-flight
- **Auditor-Q5:** 8 banked + 1 in-flight (P0.S4 9th in-flight projection)
- **Deferred-canary strategy:** 3rd application → **4th application** in flight at closure

---

## 10. Plan v1 forecast

Plan v1 will lock:
- Scope decision on D1 extending to Kuzu `_create_edge` (Phase 0 recommendation: YES)
- Scope decision on D2 scanning `_visibility_clause` only vs all `'privacy_level'` SQL literal sites (Phase 0 recommendation: only `_visibility_clause`)
- Exact `ValueError` message text + format
- D2 AST filter precise regex (handle edge cases in string-literal extraction)
- Test count refinement (Phase 0 forecasts 7 logical anchors → ~28-30 collected with parametrize)
- Plan v2 likely needed for medium-spec — D1 + D2 + D3 each have surface-detail precision items the auditor will surface

**Expected cadence:** v1 → v2 → developer per strict-mode §8 sub-rule hypothesis (3-D-decision medium-spec). NOT the OPTIONAL-Plan-v2 path P0.S3 validated for 1-2 D-decision specs.

**Estimated developer effort:** ~2-3 hours (single Python file modification + tests). Smaller than P0.S2/P0.S3 but larger than the OPTIONAL-Plan-v2 minimum.

---

**End of Phase 0 audit.**

Ready to share with auditor. Standard sequence: this audit → auditor review → Plan v1 with precision items → auditor review → Plan v2 (likely, given 3-D-decision scope) → joint sign-off → developer → closure.

**Discipline banking at Phase 0 land:**
- **`### Phase-0-catches-wrong-premise` 6th instance** — first banked instance since the 5-instance threshold-crossing doctrine elevation. The doctrine's "future accumulation" clause activates as designed.
