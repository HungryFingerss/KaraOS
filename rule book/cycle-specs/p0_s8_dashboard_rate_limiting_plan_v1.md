# P0.S8 Plan v1 — Dashboard rate limiting (D1-D4 contract lock + ORDERING INVARIANT)

**Phase 0 base:** `tests/p0_s8_dashboard_rate_limiting_audit.md` (auditor APPROVED 2026-05-22 with all 4 open questions adjudicated to architect leans + Q5 band locked at 3-7 mid 5 + 0 open precision items at Phase 0 review).

**Phase 0 outcomes:** 6th instance of `### Zero-precision-items-at-auditor-review` (1 from elevation event). New informal observation `User-WONTFIX-after-design-dialogue` 1st instance banked at Phase 0 close. 5th OPTIONAL-Plan-v2 proof case candidate locked — would activate DOCTRINE ELEVATION CANDIDACY if Plan v1 clears 0 items.

**Plan v1 absorbs (proactively, all 4 anticipated precision items from auditor verdict):**

- **P1** §1 — Pass-2 grep enumeration of `dog-ai-dashboard/` dependency surface + middleware composition surface.
- **P2** §2.2 — LRUCache config locked (max=100, ttl=60_000ms, key=string, value=number[] timestamp array).
- **P3** §2.3 + §2.4 — Sliding-window logic + **ORDERING INVARIANT comment template** (10-step verbatim per P0.B2/P0.B3 precedent; load-bearing per auditor verdict — "rate-limit MUST run AFTER auth check" is non-negotiable security-spec discipline).
- **P4** §5 — Closure-narrative paste-template (5-surface landing format) + §12 closure-conditional doctrine elevation pre-draft for `### Plan-v2-optional-on-clean-cross-actor-pre-emption` (5th proof case at P0.S8 closure if Plan v1 clears cleanly).

Cadence prediction: **v1 only OPTIONAL-Plan-v2 path candidate (5th proof case if Plan v1 absorbs cleanly)** — would mature path to 5+ doctrine elevation candidacy. Realistic alternative per auditor: security-spec cycles historically required Plan v2; if auditor surfaces ≥1 unresolved item, escalate to Plan v2.

---

## §1. P1 — Pass-2 grep enumeration across dashboard subsystem

### §1.1 Dependency surface (lru-cache install target)

**File:** `dog-ai-dashboard/package.json` (15 dependencies, no test deps).

Current state (Phase 0 §1.2 verified):
- `dependencies`: `next` 14.2.5, `react` ^18.3.1, `react-dom` ^18.3.1, `better-sqlite3` ^11.1.2, `lucide-react` ^0.383.0.
- `devDependencies`: `@types/node`, `@types/react`, `@types/react-dom`, `@types/better-sqlite3`, `autoprefixer`, `postcss`, `tailwindcss`, `typescript`.

**D1 add:** `"lru-cache": "^10.x"` to `dependencies`. Run `npm install` to update `package-lock.json` + actually pull the package into `dog-ai-dashboard/node_modules/`.

**Pass-2 verification needed at Phase 4**: developer confirms package-lock.json reflects the new dep + `node_modules/lru-cache/` exists post-install + TypeScript type-check passes (lru-cache v10 ships its own .d.ts types; no `@types/lru-cache` needed in devDeps).

### §1.2 Middleware composition surface

**File:** `dog-ai-dashboard/middleware.ts` (Phase 0 §1.1 verified — 89 lines).

**Insertion points** (LOCKED for D2/D3/D4):
- Import addition (~line 21-24 alongside existing imports): `import { LRUCache } from 'lru-cache'`.
- Module-level LRUCache instance (BEFORE `function middleware(req)` at line 42): the cache instance declaration.
- Rate-limit check inside `middleware(req)`: AFTER `_safeEqual` validation (line 75) but BEFORE `NextResponse.next()` pass-through (line 80).

**Pass-2 verification needed at Plan v1:** the existing `middleware(req)` function has 3 early-return paths (line 48 `/api/auth` carve-out, line 60-64 file-read error → 401, line 71 absent-cookie → 401, line 76 mismatch → 401). Rate-limit check sits AFTER all 4 early-returns (only validated-auth requests reach the rate-limit logic).

### §1.3 Existing test surface

**File:** `tests/test_dashboard_middleware.py` (Phase 0 §1.3 verified — 7 source-inspection tests covering matcher coverage + 401 paths + token-file-read invariant + factory-reset gating).

**D4 add NEW tests** to this file (or sibling `tests/test_dashboard_rate_limit.py`). Architect lean: same file `test_dashboard_middleware.py` (rate-limit IS middleware behavior; same source-inspection pattern; same `middleware_src` fixture). Plan v1 lock: same file.

### §1.4 Sibling files for Twin-filename check

**Pass-2 grep**: `tests/` for any `*rate*limit*.py` OR `*rate_limit*.py` files. None found.

**dashboard side**: `dog-ai-dashboard/lib/` for any existing `rate-limit*.ts` files. None found.

Twin-filename pitfall — clean: no naming-collision risk. 11th preventive instance.

---

## §2. D-decisions — full contract lock

### §2.1 D1 LOCK — Install lru-cache dependency

**File:** `dog-ai-dashboard/package.json`.

**Edit:** add to `dependencies`:

```json
"dependencies": {
  "better-sqlite3": "^11.1.2",
  "lru-cache": "^10.x",
  "lucide-react": "^0.383.0",
  "next": "14.2.5",
  "react": "^18.3.1",
  "react-dom": "^18.3.1"
}
```

(Keep alphabetical ordering — `lru-cache` lands between `better-sqlite3` and `lucide-react`.)

**Post-edit**: run `npm install` to update `package-lock.json` + populate `node_modules/lru-cache/`.

**Discipline anchor**: D4 source-inspection test reads `package.json` + asserts `lru-cache` is in `dependencies`.

### §2.2 D2 LOCK — LRUCache instance config

**File:** `dog-ai-dashboard/middleware.ts` (module-level declaration BEFORE `function middleware`).

**Edit:**

```typescript
// P0.S8 D2 — rate-limit cache. Key = validated dogai_session cookie value
// (post-_safeEqual auth check); value = sliding-window timestamp array.
// max=100 is conservative for single-user dashboard cardinality (~1-2
// active entries typical); ttl=60_000ms aligns with the 60s rate-limit
// window so stale entries auto-evict. Module-level — state resets on
// dashboard restart (acceptable; rate-limit state is ephemeral by design
// per P0.S8 Phase 0 §3.3).
import { LRUCache } from 'lru-cache'

const _rateLimitCache = new LRUCache<string, number[]>({
  max: 100,
  ttl: 60_000,
})
```

**Discipline anchors**:
- D4 source-inspection test asserts `import { LRUCache } from 'lru-cache'` present.
- D4 source-inspection test asserts `new LRUCache<string, number[]>` with `max: 100` + `ttl: 60_000` config.

### §2.3 D3 LOCK — Sliding-window logic + 429 response

**File:** `dog-ai-dashboard/middleware.ts` (inside `middleware(req)` AFTER `_safeEqual` at line 75, BEFORE `NextResponse.next()` at line 80).

**Edit (the rate-limit block):**

```typescript
  // Constant-time compare. Length pre-check + timingSafeEqual.
  if (!_safeEqual(cookieValue, fileToken)) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  // P0.S8 D3 ORDERING INVARIANT (Bug stub at complete-plan.md:639-642
  // + auditor Phase 0 verdict 2026-05-22 lock): rate-limit check MUST
  // run AFTER `_safeEqual` validation. Pre-fix: no rate-limit at all
  // (the bug). Post-fix: rate-limit AFTER auth, so failed-auth requests
  // (returning 401 above) DO NOT populate the LRUCache + DO NOT consume
  // the per-token rate-limit budget. This is the load-bearing security
  // invariant per auditor verdict — moving rate-limit BEFORE auth would
  // allow unauthenticated requests to flood the LRUCache (bypassing the
  // per-token semantic + creating DoS vector against rate-limit state).
  //
  // ORDERING INVARIANT steps (10-step verbatim per P0.B2/P0.B3 template):
  //   1. /api/auth carve-out short-circuit (line 47) — un-gated by design.
  //   2. File-read of .dashboard_token (line 54) — ENOENT → 401.
  //   3. Cookie extraction (line 69) — absent → 401.
  //   4. _safeEqual compare (line 75) — mismatch → 401.
  //   5. THIS RATE-LIMIT BLOCK — only validated cookies reach this point.
  //   6. Fetch timestamp array from cache (cookieValue key).
  //   7. Filter timestamps within 60s window (sliding-window logic).
  //   8. If window count >= 60 → return 429 with Retry-After.
  //   9. Else: append current timestamp + write back to cache.
  //  10. Pass through to NextResponse.next() (line 80 below).
  const now = Date.now()
  const windowMs = 60_000
  const limit = 60
  const timestamps = _rateLimitCache.get(cookieValue) ?? []
  const recent = timestamps.filter((ts) => now - ts < windowMs)
  if (recent.length >= limit) {
    const oldest = recent[0]
    const retryAfterSecs = Math.ceil((oldest + windowMs - now) / 1000)
    return NextResponse.json(
      { error: 'Rate limit exceeded', retry_after_seconds: retryAfterSecs },
      {
        status: 429,
        headers: { 'Retry-After': String(retryAfterSecs) },
      }
    )
  }
  recent.push(now)
  _rateLimitCache.set(cookieValue, recent)

  // Authenticated AND within rate limit — pass through.
  return NextResponse.next()
```

**Discipline anchors**:
- D4 AST/source-inspection test asserts the rate-limit block sits AFTER the `_safeEqual` line + BEFORE the final `NextResponse.next()`.
- D4 source-inspection test asserts `status: 429` + `Retry-After` header + `retry_after_seconds` JSON field.
- D4 source-inspection test asserts the ORDERING INVARIANT comment block contains "rate-limit check MUST run AFTER `_safeEqual`" verbatim language.

### §2.4 D4 LOCK — Source-inspection test surface

**File:** `tests/test_dashboard_middleware.py` (extend existing file; same `middleware_src` fixture pattern as P0.S2 tests).

**5 NEW test functions:**

**D4 Anchor 1 — `test_p0_s8_d1_lru_cache_dependency_added`:**

```python
def test_p0_s8_d1_lru_cache_dependency_added():
    """P0.S8 D1: dog-ai-dashboard/package.json must declare lru-cache dependency."""
    import json
    from pathlib import Path
    pkg = json.loads(Path("dog-ai-dashboard/package.json").read_text(encoding="utf-8"))
    deps = pkg.get("dependencies", {})
    assert "lru-cache" in deps, (
        "P0.S8 D1: lru-cache must be in dog-ai-dashboard/package.json dependencies"
    )
    # Version pin: ^10.x or compatible. Reject obviously-wrong versions.
    version = deps["lru-cache"]
    assert version.startswith("^10") or version.startswith("10"), (
        f"P0.S8 D1: lru-cache version should be ^10.x per Q1 LOCK; got {version!r}"
    )
```

**D4 Anchor 2 — `test_p0_s8_d2_lru_cache_instance_config(middleware_src)`:**

```python
def test_p0_s8_d2_lru_cache_instance_config(middleware_src):
    """P0.S8 D2: middleware.ts declares LRUCache<string, number[]> with max=100, ttl=60_000."""
    # Import present.
    assert "import { LRUCache } from 'lru-cache'" in middleware_src, (
        "P0.S8 D2: middleware.ts must import LRUCache from lru-cache"
    )
    # Instance declared at module scope.
    assert "new LRUCache<string, number[]>" in middleware_src, (
        "P0.S8 D2: LRUCache instance must use <string, number[]> type parameters"
    )
    # Config: max=100, ttl=60_000.
    assert "max: 100" in middleware_src, (
        "P0.S8 D2 Q2 LOCK: LRUCache max must be 100"
    )
    assert "ttl: 60_000" in middleware_src or "ttl: 60000" in middleware_src, (
        "P0.S8 D2: LRUCache ttl must be 60_000 (or 60000) ms"
    )
```

**D4 Anchor 3 — `test_p0_s8_d3_rate_limit_after_auth_ordering_invariant(middleware_src)` (LOAD-BEARING per auditor):**

```python
def test_p0_s8_d3_rate_limit_after_auth_ordering_invariant(middleware_src):
    """P0.S8 D3 ORDERING INVARIANT (load-bearing per auditor Phase 0 verdict):
    rate-limit check MUST sit AFTER _safeEqual validation in middleware(req).

    Pre-fix: no rate-limit (the bug). Post-fix: rate-limit AFTER auth so
    failed-auth requests do NOT populate the LRUCache + do NOT consume
    per-token rate-limit budget. Moving rate-limit BEFORE auth would
    allow unauthenticated requests to flood the LRUCache (bypassing
    per-token semantic + creating DoS vector against rate-limit state).
    """
    # Find positions of key landmarks in the middleware source.
    safeequal_idx = middleware_src.find("_safeEqual(cookieValue, fileToken)")
    rate_limit_idx = middleware_src.find("_rateLimitCache.get(cookieValue)")
    pass_through_idx = middleware_src.find("// Authenticated AND within rate limit")
    assert safeequal_idx > 0, (
        "P0.S8 D3: _safeEqual(cookieValue, fileToken) call must be present"
    )
    assert rate_limit_idx > 0, (
        "P0.S8 D3: _rateLimitCache.get(cookieValue) call must be present"
    )
    assert pass_through_idx > 0, (
        "P0.S8 D3: pass-through comment 'Authenticated AND within rate limit' must be present"
    )
    assert safeequal_idx < rate_limit_idx < pass_through_idx, (
        f"P0.S8 D3 ORDERING INVARIANT violation: rate-limit check must sit "
        f"AFTER _safeEqual validation (idx={safeequal_idx}) and BEFORE pass-through "
        f"(idx={pass_through_idx}); got rate-limit at idx={rate_limit_idx}."
    )
    # ORDERING INVARIANT comment block must be present.
    assert "ORDERING INVARIANT" in middleware_src, (
        "P0.S8 D3: ORDERING INVARIANT comment block must document the rate-limit-AFTER-auth rule"
    )
    assert "rate-limit check MUST run AFTER" in middleware_src, (
        "P0.S8 D3: ORDERING INVARIANT comment must contain the verbatim load-bearing assertion"
    )
```

**D4 Anchor 4 — `test_p0_s8_d3_sliding_window_logic(middleware_src)`:**

```python
def test_p0_s8_d3_sliding_window_logic(middleware_src):
    """P0.S8 D3: sliding-window logic — 60 req/min via timestamp array filter."""
    assert "now - ts < windowMs" in middleware_src or "now - ts < 60" in middleware_src, (
        "P0.S8 D3: sliding-window filter must compare timestamps against 60s window"
    )
    assert "windowMs = 60_000" in middleware_src or "windowMs = 60000" in middleware_src, (
        "P0.S8 D3: windowMs constant must be 60_000 (or 60000) per spec"
    )
    assert "limit = 60" in middleware_src, (
        "P0.S8 D3: rate-limit threshold must be 60 per spec"
    )
    assert "recent.length >= limit" in middleware_src, (
        "P0.S8 D3: rate-limit gate must reject when timestamp count >= 60"
    )
```

**D4 Anchor 5 — `test_p0_s8_d3_429_response_shape(middleware_src)`:**

```python
def test_p0_s8_d3_429_response_shape(middleware_src):
    """P0.S8 D3: 429 response includes Retry-After header + retry_after_seconds JSON field."""
    assert "status: 429" in middleware_src, (
        "P0.S8 D3: 429 status code must be used for rate-limit-exceeded response"
    )
    assert "'Retry-After'" in middleware_src or '"Retry-After"' in middleware_src, (
        "P0.S8 D3: Retry-After header must be set on 429 response"
    )
    assert "retry_after_seconds" in middleware_src, (
        "P0.S8 D3: retry_after_seconds JSON field must be in 429 response body"
    )
    assert "'Rate limit exceeded'" in middleware_src or '"Rate limit exceeded"' in middleware_src, (
        "P0.S8 D3: 429 error message must be 'Rate limit exceeded'"
    )
```

### §2.5 Deliberate-regression checks (induction-surfaces-invariant-gaps protocol)

Phase 4 must execute:
- (a) Move the rate-limit block BEFORE the `_safeEqual` line → D4 Anchor 3 ORDERING INVARIANT fails with positional violation.
- (b) Change `max: 100` to `max: 1000` → D4 Anchor 2 fails.
- (c) Change `limit = 60` to `limit = 30` → D4 Anchor 4 fails.
- (d) Drop the `Retry-After` header → D4 Anchor 5 fails.
- (e) Remove `lru-cache` from package.json → D4 Anchor 1 fails.

All 5 reverts confirm structural invariants are correctly anchored.

---

## §3. Test surface — 5 anchors

| D-decision | Anchor type | Count |
|---|---|---|
| D1 (package.json) | Source-inspection: lru-cache in dependencies | 1 |
| D2 (LRUCache config) | Source-inspection: import + instance + max=100 + ttl=60_000 | 1 |
| D3 (ordering invariant) | **LOAD-BEARING** source-inspection: rate-limit AFTER `_safeEqual` + ORDERING INVARIANT comment | 1 |
| D3 (sliding-window logic) | Source-inspection: windowMs + limit + filter + reject pattern | 1 |
| D3 (429 response shape) | Source-inspection: status 429 + Retry-After + retry_after_seconds + error text | 1 |
| **TOTAL** | | **5** |

**Q5 LOCK: 5 anchors.** Auditor Q5 band 3-7 mid 5. Locked-actual 5 = 0% (exact mid) = **ON-TARGET** per Plan v3 §1.1 corrected band table. 3rd consecutive exact-mid 0% reading after P0.B5 + P0.B6.

---

## §4. Closure-actual projection per Explicit-closure-honest-count-commitment (11th instance MADE here)

**Architect commits BEFORE closure** per `Explicit-closure-honest-count-commitment` discipline (11th instance candidate, to be HONORED at closure-audit as 12th instance per STRICT separation):

Honest closure-actual count is the binding number. Per §3 band table:

| Closure-actual | Math (vs mid 5) | Disposition | Doctrine effect |
|---|---|---|---|
| ≤3 anchors | `≤−40%` | **FALSIFICATION TRIGGER** | **DEMOTES 11 → 10 supporting** |
| 4 anchors | `−20%` | **SLIGHT-DRIFT-DOWN** | HOLDS at 11 (no bump, no demote) |
| **5 anchors (Plan v1 LOCK)** | `0%` | **ON-TARGET** | **BUMPS 11 → 12 supporting** |
| 6 anchors | `+20%` | **SLIGHT-DRIFT-UP** | HOLDS at 11 (no bump, no demote) |
| ≥7 anchors | `≥+40%` | **FALSIFICATION TRIGGER** | **DEMOTES 11 → 10 supporting** |

Band definitions per Plan v3 §1.1 corrected band table:
- ±15% ON-TARGET = [4.25, 5.75] → only 5 anchors qualifies.
- ±15% to ±30% SLIGHT-DRIFT = 4 or 6 anchors.
- ≥±30% FALSIFICATION = ≤3 or ≥7 anchors.

NARROW ON-TARGET band — only exact 5 bumps doctrine.

Honest acknowledgment: if Phase 4 surfaces a 6th anchor (e.g. D4 Anchor 6 covers an additional structural property not yet enumerated), closure-actual lands SLIGHT-DRIFT-UP. Or if D4 Anchor 4+5 collapse into a single parametrized test, closure-actual lands SLIGHT-DRIFT-DOWN. Honest reading applied regardless.

---

## §5. P4 — Closure-narrative paste-template (5-surface landing per P0.B3/P0.B5/P0.B6 precedent)

When P0.S8 closes, the closure narrative MUST land verbatim across these 5 surfaces:

### §5.1 CLAUDE.md line ~3

```
| **P0.S8 (Dashboard rate limiting via lru-cache middleware) CLOSED 2026-05-XX** — Closes the rate-limit gap on the dashboard side. 4 D-decisions across single subsystem (dog-ai-dashboard/middleware.ts) + 1 new dependency. D1: lru-cache ^10.x added to package.json. D2: module-level LRUCache<string, number[]> with max=100, ttl=60_000ms keyed by validated dogai_session cookie. D3: sliding-window logic (60 req/60s) AFTER _safeEqual validation per LOAD-BEARING ORDERING INVARIANT (rate-limit-AFTER-auth prevents unauth requests from flooding the cache + creating DoS vector against rate-limit state). 429 response with Retry-After header + retry_after_seconds JSON field. D4: 5 source-inspection tests at tests/test_dashboard_middleware.py covering D1+D2+D3+ordering invariant + sliding-window logic + 429 shape. 5 logical anchors = Plan v1 §3 LOCK exact match. Q5 closure 0% ON-TARGET (3rd consecutive exact-mid 0% after P0.B5 + P0.B6) → doctrine ### Phase-0-granular-decomposition-enables-accurate-estimates BUMPS 11 → 12 supporting. Plan v1 §4 honest-count commitment HONORED — 11th instance MADE + 12th HONORED. **5th OPTIONAL-Plan-v2 proof case** (P0.S3 + P0.B3 + P0.B5 + P0.B6 + P0.S8) → DOCTRINE ELEVATION CANDIDACY REACHED for ### Plan-v2-optional-on-clean-cross-actor-pre-emption — pre-draft locked at Plan v1 §12 verbatim ready for elevation if 4-criteria architect closure-audit ratifies. ### Zero-precision-items-at-auditor-review 5 → 7 instances (Phase 0 6th + Plan v1 7th + closure 8th if cleared). NEW informal observations: User-WONTFIX-after-design-dialogue (1st instance, Bug 5/P0.B1.X resolution 2026-05-21). Twin-filename pitfall 11th preventive event. NOT-IN-SCOPE: multi-worker shared state, per-route differentiated limits, /api/auth brute-force protection (deferred to P0.S8.X if surfaces).
```

### §5.2-§5.4 parent + subdir `complete-plan.md` + `to_be_checked.md`

Per P0.B3/P0.B5/P0.B6 precedents. Twin-filename pitfall discipline at status flip (parent + subdir).

### §5.5 Memory files

- `feedback_explicit_closure_honest_count_commitment.md`: bump 10 → 12 instances (Plan v1 §4 MADE 11th + closure HONORED 12th per STRICT).
- `feedback_phase_0_zero_precision_items_at_auditor_review.md`: bump 5 → 7+ if Phase 0 + Plan v1 + closure all clear at 0 items each (track-record extension).
- `feedback_user_wontfix_after_design_dialogue.md`: stays 1 instance (no new event at P0.S8).

---

## §6. Cross-spec impact analysis

See Phase 0 §5 — verified clean. P0.S2 closed dependency provides cookie-value-as-rate-limit-key compose surface. P0.0.1/P0.0/P1.A orthogonal. NOT-IN-SCOPE explicitly enumerated.

---

## §7. Quality gate checklist (10 APPLIES + 1 N/A privacy)

Per strict-mode 11-gate floor:

1. ✅ Phase 0 audit completed + auditor-approved with 0 open precision items (6th `Zero-precision-items` instance).
2. ✅ Plan v1 absorbs all 4 anticipated precision items proactively (P1 Pass-2 grep + P2 LRUCache config + P3 ORDERING INVARIANT comment template + P4 closure-narrative paste-template).
3. ✅ D-decisions have unambiguous contracts — D1 at §2.1 + D2 at §2.2 + D3 at §2.3 + D4 at §2.4.
4. ✅ Pre-mortem coverage — 7 failure modes documented at Phase 0 §3.
5. ✅ Multi-direction invariant trace per D-decision — Phase 0 §4.
6. ✅ Cross-spec impact analysis — Phase 0 §5.
7. ✅ Spec-time grep-verification (Pass-1 + Pass-2) — Phase 0 §1 (Pass-1) + Plan v1 §1 (Pass-2). 24th instance at Plan v1 close.
8. ✅ Honest-closure-actual-count commitment made at Plan v1 §4 — 11th instance to be banked.
9. ✅ Deliberate-regression check protocol — §2.5 enumerates 5 induced reverts.
10. ✅ Closure-narrative paste-template ready — §5 5-surface template + §3 band-table.
11. N/A Privacy — dashboard rate-limit operates on opaque cookie values; no PII path.

---

## §8. Discipline counts at Plan v1 close

| Discipline | Phase 0 close | Plan v1 close |
|---|---|---|
| Spec-first review cycle | 56 | **57** ✓ |
| Strict-industry-standard mode | 46 + 13 closures | **47 applications + 13 closures** ✓ |
| `### Phase-0-granular-decomposition-enables-accurate-estimates` | 11 supporting | stays 11 (closure pending; ON-TARGET candidate at 5 anchors → bump 11→12) |
| `### Phase-0-catches-wrong-premise` | 8 | stays 8 |
| `### Twin-filename-pitfall-prevention` | 7 + 4 op rules | stays 7 (11th preventive event but doctrine count holds per instance-enumeration rule) |
| `### Grep-baseline-before-drafting` | 13 | **14** ✓ |
| `### Zero-precision-items-at-auditor-review` (elevated doctrine) | 5 at elevation | stays 5 (Plan v1 audit pending; if 0 items → 6th instance) |
| Deferred-canary | 15th in-flight | stays 15 (closure event pending) |
| Auditor-Q5-estimates-trail-grep | 17 banked | stays 17 + 1 in-flight |
| Cross-cycle-handoff transparency precedent | 19 successful | **20 successful** ✓ |
| Architect-reads-production-code-before-sign-off | 10 banked | stays 10 (closure-audit pending) |
| Sub-pattern A | 8 | stays 8 |
| Spec-time grep-verification | 23 instances | **24** ✓ |
| Discipline-count-bump-needs-explicit-justification | 11 preventive | stays 11 |
| Convention-drift-on-discipline-counts | 5 | stays 5 |
| Per-artifact-arithmetic-drift-survives-grep-baseline | 1 | stays 1 |
| `Explicit-closure-honest-count-commitment` | 10 | **11** ✓ (Plan v1 §4 commitment MADE) |
| `Auditor-catches-Q5-math-at-plan-review` | 2 | stays 2 |
| `Plan-v1-Pass-2-grep-undercount` | 3 | stays 3 |
| `Bug-fix-cycles-surface-discipline-edges` | 1 | stays 1 |
| `Auditor-adjudication-drift-clarified-by-architect` | 2 | stays 2 |
| `Stale-TODO-marker-after-work-complete` | 2 | stays 2 |
| `Board-meeting-attack-premise-needs-grep-verification` | 1 | stays 1 |
| `User-WONTFIX-after-design-dialogue` (NEW) | 1 | stays 1 |
| OPTIONAL-Plan-v2 proof case | 4 | stays 4 (closure-conditional 5th → DOCTRINE ELEVATION CANDIDACY) |
| HEAVY-band cadence | 2 | stays 2 (P0.S8 SMALL-band) |

---

## §9. Open questions for auditor (0)

No new open questions. Plan v1 absorbs all 4 anticipated precision items proactively. Architect prediction: **APPROVED 0 items → ship to developer per OPTIONAL-Plan-v2 path (5th proof case → DOCTRINE ELEVATION CANDIDACY)**.

---

## §10. Implementation handoff readiness

**Developer contract:**
- **Scope:** D1 + D2 + D3 + D4 per §2.1-§2.4.
- **Estimated effort:** 2-3 hours (SMALL-band single-subsystem; 1 dependency install + ~50 LOC middleware additions + 5 source-inspection tests).
- **Files touched:** `dog-ai-dashboard/package.json` (D1) + `dog-ai-dashboard/middleware.ts` (D2 + D3) + `tests/test_dashboard_middleware.py` (D4) + `dog-ai-dashboard/package-lock.json` (regenerated by npm install).
- **Phase 1 (~15 min)**: D1 npm install lru-cache + verify TypeScript build still passes.
- **Phase 2 (~30 min)**: D2 LRUCache instance declaration at module scope.
- **Phase 3 (~45 min)**: D3 sliding-window logic + ORDERING INVARIANT comment block + 429 response.
- **Phase 4 (~30 min)**: D4 5 source-inspection tests.
- **Phase 5 (~30 min)**: §2.5 deliberate-regression confirmations (a/b/c/d/e all must fire correctly).
- **Phase 6 (~30 min)**: closure narrative + 5-surface landing + memory bankings + architect closure-audit + DOCTRINE ELEVATION if 4-criteria ratification passes.

---

## §11. Open invariants for Plan v1 to enumerate

1. **D1 dependency-presence invariant** — `lru-cache` in `dog-ai-dashboard/package.json` dependencies.
2. **D2 LRUCache-config invariant** — `max: 100` + `ttl: 60_000` + `<string, number[]>` type parameters.
3. **D3 ORDERING INVARIANT** — rate-limit block sits AFTER `_safeEqual` validation (load-bearing per auditor; positional source-inspection test enforces).
4. **D3 sliding-window-logic invariant** — `windowMs = 60_000` + `limit = 60` + `recent.length >= limit` rejection pattern.
5. **D3 429-response-shape invariant** — `status: 429` + `Retry-After` header + `retry_after_seconds` JSON field.
6. **No-side-effect-in-Phase-0 invariant** — Phase 0 audit landed with zero production code changes.

---

## §12. Closure-conditional doctrine elevation candidate — `### Plan-v2-optional-on-clean-cross-actor-pre-emption`

Per auditor Plan v1 verdict 2026-05-22 (anticipated): OPTIONAL-Plan-v2 reaches 5 instances at P0.S8 close → DOCTRINE ELEVATION CANDIDACY. **Pre-draft locked here per Twin-filename / Grep-baseline / Zero-precision-items doctrine pre-draft precedents (P0.S7 / P0.B3 / P0.B6).**

**Closure-conditional contract:** if at P0.S8 closure ALL FOUR criteria are confirmed —
1. 5 instances confirmed (P0.S3 + P0.B3 + P0.B5 + P0.B6 + P0.S8)
2. Discipline-stability across 5 applications (no silent drift; OPTIONAL-Plan-v2 path applied cleanly each time without scope creep)
3. Cross-actor validation (auditor confirmed acceptance via clean Plan v1 verdicts on each cycle)
4. No false-positive flags (no cycle where OPTIONAL-Plan-v2 was claimed but Plan v2 actually shipped)

— THEN elevate to numbered CLAUDE.md doctrine at P0.S8 closure narrative with VERBATIM text per §12.1 below.

### §12.1 Pre-draft doctrine text (VERBATIM-LOCK candidate)

```markdown
### Plan-v2-optional-on-clean-cross-actor-pre-emption

When Phase 0 + Plan v1 absorb anticipated precision items proactively
+ Q5 math holds + cross-spec interactions are clean + auditor returns
0 items at Plan v1 review, the cycle ships to developer WITHOUT Plan
v2. The Plan-v2 ritual is replaced by clean cross-actor pre-emption:
architect's Phase 0 audit + Plan v1 anticipate the auditor's likely
precision items proactively; auditor's review confirms 0 gaps; cycle
proceeds to developer directly.

Applies across SMALL + MEDIUM bands when architectural complexity is
LOW per-D-decision. Does NOT apply to HEAVY-band cycles (where the
multi-axis cadence working hypothesis predicts v3 floor — see
`feedback_plan_version_cadence_multi_axis.md`).

**Track record (5 instances at elevation 2026-05-XX):**

- **P0.S3 (2026-05-20):** 1st instance — SMALL-band; classifier scenario
  prompt cleanup; Plan v1 cleared 0 items; OPTIONAL-Plan-v2 path
  established as concrete proof case.
- **P0.B3 (2026-05-21):** 2nd instance — SMALL-band; Kuzu schema
  migration ordering + Health observable; Plan v1 cleared 0 items.
- **P0.B5 (2026-05-21):** 3rd instance — FIRST MEDIUM-band proof case;
  4 D-decisions across 4 subsystems (Resilience Hygiene Bundle); broke
  the small-band-only assumption. Refined hypothesis to
  "low-architectural-complexity-band" across D-count tiers.
- **P0.B6 (2026-05-21):** 4th instance — SMALL-band; documentation-
  correctness cycle (skeptic1 Attack 3 falsified premise + 23rd-rule
  AST tripwire).
- **P0.S8 (2026-05-XX):** 5th instance — SMALL-band security spec
  (dashboard rate limiting). Elevation event ratified per §12.3
  architect closure-audit 4-criteria verification.

**Discipline-stability evidence (auditor adjudication at P0.S8 Plan v1
verdict 2026-05-22):**

The discipline was applied CONSISTENTLY across 5 cycles without silent
drift. No cycle claimed OPTIONAL-Plan-v2 path but actually shipped
Plan v2 (no false-positive). Cross-actor validation: pattern co-
discovered (architect proactively absorbs anticipated items + auditor
confirms via clean Plan v1 verdict with explicit ACCEPT on each cycle).

**Operational rules:**

1. The architect's Plan v1 must absorb all anticipated precision items
   proactively (multi-pattern Pass-2 grep + closure-template lock + AST
   tripwire shape + cross-spec impact + Q5 band-table + explicit open
   questions with architect leans).
2. If auditor returns 0 precision items at Plan v1 review → cycle ships
   to developer directly (no Plan v2).
3. If auditor surfaces ≥1 unresolved item at Plan v1 review → cycle
   escalates to Plan v2 normally.
4. The OPTIONAL-Plan-v2 path does NOT apply to HEAVY-band cycles per
   the multi-axis cadence working hypothesis.

**Structural relationship to `### Zero-precision-items-at-auditor-review`:**

The two doctrines describe the same operational floor from different
angles:
- `Zero-precision-items` names the AUDITOR-SIDE observation (auditor
  returns 0 items).
- `Plan-v2-optional-on-clean-cross-actor-pre-emption` names the
  CYCLE-SHAPE consequence (cycle skips Plan v2).

Both are required for OPTIONAL-Plan-v2 path. They are non-overlapping
descriptions of the same property; both are banked because future
analysis may need either lens (auditor-process focus vs cycle-cadence
focus).

**Cross-disciplines:**

- `### Zero-precision-items-at-auditor-review` (CLAUDE.md, 5 instances
  at elevation; 6th instance pending P0.S8 Plan v1): upstream
  observation.
- `### Phase-0-granular-decomposition-enables-accurate-estimates`
  (CLAUDE.md): upstream cause — granular decomposition produces
  narrow Q5 estimates AND pre-empts auditor questions, enabling clean
  v1 absorption.
- `### Grep-baseline-before-drafting` (CLAUDE.md): contributes to
  clean Plan v1 absorption.
- `feedback_strict_industry_standard_mode.md` §8 sub-rule: original
  OPTIONAL-Plan-v2 path was defined here; this doctrine ratifies the
  sub-rule at elevation.

**Falsification clause (locked at elevation, mirrors the other 4
elevated doctrines):**

If a future instance reveals the 5-instance threshold was incorrectly
counted (e.g., one of the 5 "instances" was actually a Plan v2 cycle
mislabeled as OPTIONAL-Plan-v2), the doctrine demotes back to
informal observation + the falsification banking applies.
Specifically: a future cycle where Plan v1 cleared 0 items but the
developer reported a Plan v2 having been authored would falsify the
discipline (the "no Plan v2" claim is the load-bearing property).

**Future instances** continue to be banked under this doctrine's
track record. The doctrine matures rather than re-elevating at higher
thresholds.
```

End of elevation pre-draft.

### §12.2 If criteria not met at closure → demotion path

If at P0.S8 closure ANY of:
- A 5-instance member is contested (e.g. P0.B5 was actually MEDIUM-band → architectural-complexity-band needs refinement),
- A false-positive flag surfaces (e.g. a previously-banked OPTIONAL-Plan-v2 case actually had a hidden Plan v2 artifact),
- Discipline-stability evidence is incomplete (silent drift in some prior cycle's claim),

then: skip the elevation, bank the failure instance, continue tracking the discipline as informal observation.

### §12.3 Architect closure-audit ratification step

At P0.S8 closure, architect MUST explicitly verify:
1. **Instance enumeration**: confirm 5 instances at the track record above are all genuine OPTIONAL-Plan-v2 cycles (no Plan v2 artifact shipped).
2. **Discipline-stability evidence**: review each of the 5 applications for any silent drift or false-positive flag.
3. **Cross-reference integrity**: verify the parent-child relationships with `Zero-precision-items-at-auditor-review` + `### Phase-0-granular-decomposition-enables-accurate-estimates` remain accurate post-elevation.
4. **Falsification clause integrity**: verify the falsification clause's load-bearing property (cycle where Plan v1 cleared but developer reported Plan v2) is testable.

If all 4 verification steps pass → elevate VERBATIM per §12.1 + bank as 6th `###`-level doctrine in CLAUDE.md Architectural Disciplines section.

If any verification step fails → defer elevation + bank failure instance.

---

**End of Plan v1.** Ready to forward to auditor.

**Architect prediction:** **APPROVED 0 items → ship to developer per OPTIONAL-Plan-v2 path** (5th proof case → DOCTRINE ELEVATION CANDIDACY REACHED if Plan v1 clears + closure ratifies).
