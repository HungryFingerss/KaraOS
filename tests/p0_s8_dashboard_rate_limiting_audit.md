# P0.S8 Phase 0 audit — Dashboard rate limiting (60 req/min per token via lru-cache middleware)

**Spec ID:** P0.S8 — security/spec track (post-bug-fix arc; first P0.S* cycle since the Board-bug remediation track CLOSED at P0.B6 2026-05-21).

**Twin-filename pitfall check:** no existing `p0_s8_*` files in `tests/`. Clean disambiguation. **11th preventive instance** of `### Twin-filename-pitfall-prevention` doctrine.

**Pre-audit premise (verbatim from parent `complete-plan.md:639-642`):**

> ### P0.S8 — No rate limiting on dashboard
> **Status:** `[OPEN]` (depends on P0.S2)
> **Fix:** lru-cache rate limiter middleware. 60 req/min per token.

Cross-spec scaffolding (from `tests/p0_s2_audit.md` + `tests/p0_s2_plan_v2.md`):

- P0.S2 (CLOSED 2026-05-20) established the per-token auth surface — `.dashboard_token` file + `dogai_session` cookie + `dog-ai-dashboard/middleware.ts` gating every `/api/*` route via `_safeEqual` constant-time compare.
- P0.S2 explicitly flagged P0.S8 as depends-on: "P0.S8 (rate limiting) when that ships — cookie value = rate-limit key."
- P0.S2 known limitation banked: cross-worker rate-limit state coordination is OUT OF SCOPE (today the dashboard is single-process; multi-worker cluster-mode would need shared state — defer until cluster mode lands).

**Cadence prediction (initial):** SMALL-band (3-4 D-decisions / single subsystem `dog-ai-dashboard/middleware.ts` + 1 NEW dependency / LOW fan-out) → **v1 only OPTIONAL-Plan-v2 path candidate** (5th proof case if Plan v1 absorbs cleanly). The bug-fix arc established OPTIONAL-Plan-v2 path as routine for clean SMALL/MEDIUM-band cycles (4 proof cases: P0.S3 + P0.B3 + P0.B5 + P0.B6).

---

## §1. Grep-verified surface (Pass-1)

### §1.1 Existing middleware surface (P0.S2 closure)

**Production surface:** `dog-ai-dashboard/middleware.ts:42-81` (function `middleware(req: NextRequest)`).

Current flow:
1. `/api/auth` allowlist short-circuit (line 47) — only un-gated route (mints the cookie).
2. Read `.dashboard_token` file fresh on every request (line 54). NO module-scope cache (P0.S2 D4 file-read invariant).
3. Extract `dogai_session` cookie value (line 69). Absent → 401.
4. `_safeEqual` constant-time compare (line 75). Mismatch → 401.
5. Pass-through (line 80).

**Matcher** (line 86-88): `'/api/:path*'` — every `/api/*` route.

**Insertion point for P0.S8:** AFTER step 4 (successful auth) but BEFORE step 5 (pass-through). Rate-limit check uses the validated cookie value as the key; failed-auth requests never reach the rate-limiter (they return 401 first).

### §1.2 Dependency surface (lru-cache)

**Production check:** `dog-ai-dashboard/package.json` does NOT contain `lru-cache` in `dependencies` or `devDependencies`. P0.S8 must ADD it.

Current dependencies (5): `next`, `react`, `react-dom`, `better-sqlite3`, `lucide-react`.

`lru-cache` is the de-facto standard Node.js LRU cache library (~5KB, MIT-licensed, well-maintained). Plan v1 will lock the version pin.

### §1.3 Existing test surface (P0.S2 closure)

**Production test files:** `tests/test_dashboard_middleware.py` (P0.S2 D3 + D4 — 7 source-inspection tests covering matcher coverage + 401 paths + token-file-read invariant + factory-reset gating).

**P0.S8 will add NEW tests** to this file (or a new sibling) covering rate-limit middleware behavior.

### §1.4 Cross-spec interactions

- **P0.S2** (closed) — middleware structure established; cookie-value-as-rate-limit-key is the locked compose surface.
- **P0.0.1** (closed) — localhost-bind tripwire at `tests/test_dashboard_bind_tripwire.py`; no interaction with rate-limit middleware (orthogonal concern: bind vs requests-per-token).
- **P1.A** (future, not yet specced) — pipeline.py + brain_agent.py decomposition; dashboard is a separate Node.js project, no interaction with P0.S8.
- **P0.S1** (open) — anti-spoof on every face match; pipeline-side, no dashboard interaction.

**Cross-spec verdict:** clean. P0.S8 is an additive middleware refinement that composes with the P0.S2-established auth flow.

---

## §2. Phase 0 verdict + D-decisions to lock

### §2.1 Phase 0 verdict: PRE-AUDIT PREMISE ON-TARGET

The spec stub at `complete-plan.md:639-642` is brief but unambiguous: lru-cache rate limiter middleware, 60 req/min per token. Grep verifies the depends-on P0.S2 surface is closed + ready to consume. No wrong-premise refinement needed. `### Phase-0-catches-wrong-premise` NOT activated this cycle (stays at 8 instances).

### §2.2 D-decisions to lock at Plan v1

**D1 (P0 CORRECTNESS — install lru-cache dependency):** Add `"lru-cache": "^10.x"` (latest stable at spec time) to `dog-ai-dashboard/package.json` `dependencies`. Run `npm install` to update `package-lock.json`. No version-pin pre-mortem — lru-cache v10 is stable; `^10.x` allows patch updates.

**D2 (P0 CORRECTNESS — rate-limit map + sliding-window logic):** Add module-level `LRUCache<string, number[]>` instance to `dog-ai-dashboard/middleware.ts` (BEFORE the `middleware` function). Key = cookie value (== `.dashboard_token` after `_safeEqual` validation). Value = `number[]` of request timestamps within the rolling 60s window. On each authenticated request:
1. Get the timestamp array for the cookie value (or empty if not present).
2. Filter out timestamps older than `now - 60_000ms`.
3. If filtered length ≥ 60 → return 429 (rate-limited).
4. Else: append current timestamp + write back to cache + pass through.

`LRUCache` options: `max: 100` (single-user dashboard; very few distinct cookie values in practice), `ttl: 60_000` (auto-evict entries idle > 60s). Module-level instance — survives Hot Module Reload in dev but resets on production restart (acceptable; rate-limit state is ephemeral by design).

**D3 (P0 OBSERVABILITY — 429 response shape):** Return `NextResponse.json({ error: 'Rate limit exceeded', retry_after_seconds: <N> }, { status: 429, headers: { 'Retry-After': '<N>' } })` where N = ceil(seconds until oldest timestamp in window expires). Standard HTTP 429 + `Retry-After` header pattern. Operator/client gets actionable signal.

**D4 (test surface — source-inspection + behavioral):** Add tests to `tests/test_dashboard_middleware.py`:
- Source-inspection: `lru-cache` imported + `LRUCache` instance declared + key=cookie-value pattern present + 429 response shape verified.
- Behavioral simulation (if testable from Python via subprocess + curl-style script): bombard a test-mode endpoint with 61+ requests in 60s; assert 60 pass + 61st returns 429. May defer to manual canary if subprocess-curl is too brittle; in that case test surface stays source-inspection only.

### §2.3 D-decisions deliberately NOT in scope

- **NOT in scope:** Multi-worker / cluster-mode shared rate-limit state. Today the dashboard runs single-process; cross-worker coordination would require Redis or similar. Defer until cluster mode lands (likely never for single-user dashboard).
- **NOT in scope:** Per-route or per-method rate limits. P0.S8 applies a single 60/min/token threshold across all `/api/*` routes (after `/api/auth` carve-out). Per-route differentiation can be added as P0.S8.X if a specific route warrants tighter/looser limits.
- **NOT in scope:** Distributed rate-limiting state (across multiple dashboard installs). Each install has its own `.dashboard_token` and thus its own isolated rate-limit space.
- **NOT in scope:** Rate-limiting the `/api/auth` endpoint itself. That route is the cookie-minting entry point + already protected by the file-token validation + has its own anti-brute-force surface (token mismatch returns 401 with no information leak). If brute-forcing `/api/auth` becomes a concern, file P0.S8.X.
- **NOT in scope:** Banning / blocking persistently-abusive tokens. P0.S8 returns 429 + Retry-After; persistent abuse would require operator intervention (rotate token).

---

## §3. Pre-mortem (7 failure modes — strict-mode floor 5-10)

### §3.1 — `/api/auth` carve-out misses rate-limit window

**Risk:** `/api/auth` short-circuits BEFORE the rate-limit check (correct — it's the cookie-minting route + has no cookie to key on). But this means an attacker can hammer `/api/auth` infinitely with bad tokens without triggering rate limit. Each hits the file-read + `_safeEqual` + returns 401.

**Mitigation:** Acceptable trade-off for P0.S8 scope. `/api/auth` is constant-time (`_safeEqual`) + returns no information about which byte mismatched. Brute-forcing a 43-char alphanumeric token is computationally infeasible (62^43 search space). If real-world brute-force attempts surface, file P0.S8.X with separate `/api/auth`-specific rate limiting (IP-based, since there's no cookie yet).

### §3.2 — Lru-cache TTL eviction race with timestamp-array logic

**Risk:** `LRUCache.ttl` evicts the entry 60s after last write. The sliding-window logic filters timestamps older than `now - 60_000`. Race: if a token's last request was 65s ago, lru-cache evicts the entry first; next request creates a NEW entry (empty array). Correct outcome (request 66 should be allowed since the prior window expired) — TTL eviction here happens to align with sliding-window semantics.

**Mitigation:** Verify the alignment at Plan v1 test design. If race surfaces, switch from `ttl: 60_000` to manual cleanup (filter array on every request; never auto-evict via TTL).

### §3.3 — Module-level cache state lost on hot-reload (dev) or restart (prod)

**Risk:** `LRUCache` instance is declared at module scope. Next.js dev server may hot-reload `middleware.ts` on edit → resets the cache → effectively grants a fresh 60-req window. Production restart also resets.

**Mitigation:** Acceptable. Rate-limit state IS ephemeral by design. A restart that wipes rate-limit state is an operational reset — not a security vulnerability. Document in middleware comments + flag at Plan v1.

### §3.4 — `LRUCache.max: 100` too small for legitimate use case

**Risk:** Today the dashboard is single-user. But a future multi-tab session, multiple browser instances, dashboard refresh patterns could push the active cookie count beyond 100 — causing legitimate cache eviction + spurious "reset" of rate-limit state.

**Mitigation:** Single-user single-token assumption holds (one `.dashboard_token` file, one cookie value). Multi-tab/window all share the same cookie. `max: 100` is conservative for the actual cardinality (typically 1-2 active entries). If wrong, Plan v1 can bump to `max: 1000` (still ~50KB worst-case).

### §3.5 — 429 response leaks rate-limit threshold info

**Risk:** Returning `Retry-After: <N>` reveals the rate-limit window to clients. A sophisticated client could probe the threshold by hammering until rate-limited.

**Mitigation:** Acceptable for a single-user dashboard. The threshold (60/min) is operator-configured; revealing it is no different from revealing the auth scheme is cookie-based. Document in Plan v1.

### §3.6 — Cookie value used as rate-limit key BEFORE constant-time-compare succeeds

**Risk:** If rate-limit check happens BEFORE `_safeEqual`, a client could send arbitrary cookie values to populate the cache + consume `max:` slots. Cache pollution / minor DoS.

**Mitigation:** D2 spec places rate-limit AFTER auth. The architect commits at Plan v1 §2 that rate-limit logic sits AFTER the `_safeEqual` check. Only validated cookies (== `.dashboard_token`) populate the cache.

### §3.7 — Sliding-window edge case: bursty traffic at minute boundary

**Risk:** Sliding-window logic: requests 1-60 land at t=0; request 61 lands at t=1ms; rate-limit fires. Now at t=60_001ms, the timestamp from t=0 falls out of the window → request 62 at t=60_002 is allowed. This means an attacker could land 60 requests at t=0 + 60 more at t=60_001 = 120 requests in 60.001 seconds. Effectively 2× the threshold at the boundary.

**Mitigation:** Sliding-window is the standard pattern; this 2x boundary spike is a known feature. Fixed-window would be even spikier (up to 2x at boundary). Token-bucket would be the alternative for stricter rate-limiting; out of P0.S8 scope. Document as acceptable.

---

## §4. Multi-direction invariant trace per D-decision

### §4.1 D1 (lru-cache dependency)

- **Forward:** middleware imports + uses LRUCache type.
- **Backward:** package.json dependency declaration; npm install regenerates package-lock.json.
- **Sideways:** other dashboard packages — no interaction (lru-cache is a leaf dependency).
- **Lifecycle:** stable; new dependency.

### §4.2 D2 (rate-limit map + sliding-window logic)

- **Forward:** rate-limit check fires on every authenticated `/api/*` request after auth.
- **Backward:** cookie value from P0.S2 `_safeEqual` is the input.
- **Sideways:** `/api/auth` short-circuit is unaffected; auth-failed requests never reach the rate-limit check.
- **Lifecycle:** module-level cache instance survives request lifecycle; resets on restart.

### §4.3 D3 (429 response shape)

- **Forward:** Next.js `NextResponse.json` with 429 status + `Retry-After` header.
- **Backward:** triggered when timestamp array length ≥ 60 within the 60s window.
- **Sideways:** standard HTTP 429 — composes with any client retry logic.
- **Lifecycle:** per-request response.

### §4.4 D4 (test surface)

- **Forward:** CI runs the tests; structural drift surfaces immediately.
- **Backward:** test reads `dog-ai-dashboard/middleware.ts` source via Python `open()` (same shape as existing P0.S2 source-inspection tests).
- **Sideways:** test file may be `tests/test_dashboard_middleware.py` extension OR a new file `tests/test_dashboard_rate_limit.py` for clean separation.
- **Lifecycle:** test runs on every PR.

---

## §5. Cross-spec impact analysis

- **P0.S2 (CLOSED 2026-05-20):** P0.S8 builds on P0.S2's middleware foundation. Cookie-value-as-rate-limit-key is the locked compose surface. No interaction conflicts.
- **P0.0.1 (CLOSED 2026-05-08):** localhost-bind tripwire is orthogonal. Rate-limit middleware sits inside the Next.js process; bind is upstream.
- **P0.0 (CLOSED 2026-05-08):** CI tiered scaffold runs Python tests on every PR; P0.S8 Python source-inspection tests integrate cleanly.
- **P1.A (future):** pipeline.py + brain_agent.py monolith decomp; dashboard is a separate Node.js project. Zero interaction.
- **Future P0.S8.X candidates** (out of scope, but bookmarked):
  - Per-route differentiated rate limits if a specific route warrants tighter/looser threshold.
  - IP-based rate limiting on `/api/auth` if brute-force attempts surface.
  - Multi-worker shared rate-limit state if cluster mode is adopted.

---

## §6. Cadence prediction

**SMALL-band (4 D-decisions, single subsystem, low fan-out, 4-6 logical anchors)** → **v1 only OPTIONAL-Plan-v2 path candidate** (5th proof case if Plan v1 absorbs cleanly).

Rationale: D1 dependency add is 1-line package.json edit + npm install. D2 rate-limit logic is ~30-40 lines of middleware additions. D3 response shape is 5-line block. D4 test surface is similar to existing P0.S2 source-inspection tests (~50 lines new test code). Total scope is comparable to P0.B6's SMALL-band cycle (4 anchors at mid).

If Plan v1 surfaces ≥1 unresolved precision item → Plan v2 escalation. Likely items: TTL-vs-manual-cleanup decision per §3.2, max-size pin per §3.4, sliding-window-vs-token-bucket per §3.7.

---

## §7. Q5 baseline estimation

Per `### Phase-0-granular-decomposition-enables-accurate-estimates` doctrine (11 supporting instances post-P0.B6):

Estimate range: **4-7 logical anchors**, mid-range **5**.

Breakdown:
- D1 (1 anchor): source-inspection that `lru-cache` is in package.json dependencies.
- D2 (2 anchors): source-inspection that `LRUCache` instance is declared + key/value pattern matches contract + rate-limit check sits AFTER `_safeEqual`.
- D3 (1-2 anchors): source-inspection that 429 response shape includes `Retry-After` header + JSON error body.
- D4 (1 anchor): if behavioral test feasible — Python subprocess + curl-style script; else folded into D2/D3 source-inspection.

**Total: 5 anchors (mid forecast)** — could land 4 (if D4 folded into D2) or 6 (if behavioral test added).

Plan v1 will lock anchor count + auditor confirms / refines mid-range.

---

## §8. Open questions for auditor (4 items)

**Q1 — `lru-cache` version pin: `^10.x` (semver-minor) vs `~10.x.x` (semver-patch) vs explicit pin?**

Architect lean: `^10.x` (allow patch + minor updates within major v10). lru-cache is well-maintained; semver-major bumps (v9 → v10) have historically been disruptive (the v10 API differs from v9). Stay on v10 line.

**Q2 — `LRUCache.max` size: 100 vs 1000?**

Architect lean: `max: 100`. Single-user dashboard; typical cardinality is 1-2 active entries. 100 is 50x overhead for safety. If cardinality surfaces higher (multi-tab patterns), Plan v1 can revise.

**Q3 — Sliding-window vs token-bucket?**

Architect lean: sliding-window per the spec stub ("60 req/min per token"). Token-bucket would be more flexible but out of scope. If real-world bursty traffic warrants smoother rate-limiting, file P0.S8.X.

**Q4 — Behavioral test surface — subprocess curl-style, or source-inspection only?**

Architect lean: source-inspection only. The middleware logic is testable via AST/regex scan against `middleware.ts`. Behavioral testing would require spinning up the dashboard process + hitting it with HTTP requests — brittle in CI (port conflicts, process lifecycle). Defer to manual canary at closure.

---

## §9. Discipline counts at Phase 0 close

**Per auditor's Post-P0.B6 ratified baseline + Phase 0 artifact (+1 per locked +1-per-artifact convention; closure-narrative arithmetic visibility refinement now applies per P0.B6 closure adjudication):**

| Discipline | Post-P0.B6 baseline | Post-P0.S8 Phase 0 |
|---|---|---|
| Spec-first review cycle | 55 | **56** ✓ (Phase 0 artifact +1) |
| Strict-industry-standard mode | 45 + 13 closures | **46 applications + 13 closures** ✓ |
| `### Phase-0-granular-decomposition-enables-accurate-estimates` | 11 supporting | stays 11 (closure pending) |
| `### Phase-0-catches-wrong-premise` | 8 | stays 8 (premise fully on-target this cycle) |
| `### Twin-filename-pitfall-prevention` | 7 + 4 op rules | stays 7 (preventive at audit drafting; 11th preventive event — counted at doctrine site honestly per the instance-enumeration rule) |
| `### Grep-baseline-before-drafting` | 12 instances | **13 instances** ✓ (Phase 0 drafted from Post-P0.B6 ratified counts) |
| `### Zero-precision-items-at-auditor-review` (5th elevated doctrine) | 5 at elevation | stays 5 (Phase 0 audit pending; if auditor returns 0 precision items → 6th instance) |
| Deferred-canary | 14th application | stays 14 (closure event pending) |
| Auditor-Q5-estimates-trail-grep | 17 banked | stays 17 (closure pending) |
| Cross-cycle-handoff transparency precedent | 18 successful | **19 successful** ✓ (architect honored P0.B6 closure verdict's ratified counts at P0.S8 baseline grep) |
| Architect-reads-production-code-before-sign-off | 10 banked | stays 10 (closure-audit pending) |
| Sub-pattern A (Phase-0-catches-wrong-premise) | 8 | stays 8 |
| Spec-time grep-verification | 22 instances | **23** ✓ (Phase 0 §1 Pass-1 grep enumerated existing middleware surface + dependency check + test surface + cross-spec checks) |
| Discipline-count-bump-needs-explicit-justification | 11 preventive | stays 11 |
| Convention-drift-on-discipline-counts (parent) | 5 | stays 5 |
| Per-artifact-arithmetic-drift-survives-grep-baseline (child) | 1 | stays 1 |
| `Explicit-closure-honest-count-commitment` | 10 | stays 10 (commitment-making pending Plan v1) |
| `Auditor-catches-Q5-math-at-plan-review` | 2 | stays 2 |
| `Plan-v1-Pass-2-grep-undercount` | 3 | stays 3 |
| `Bug-fix-cycles-surface-discipline-edges` | 1 | stays 1 (bug-fix arc closed at P0.B6; P0.S8 is post-arc work) |
| `Auditor-adjudication-drift-clarified-by-architect` | 2 | stays 2 |
| `Stale-TODO-marker-after-work-complete` | 2 | stays 2 |
| `Board-meeting-attack-premise-needs-grep-verification` | 1 | stays 1 |
| OPTIONAL-Plan-v2 proof case | 4 | stays 4 (would bump to 5 if Plan v1 absorbs cleanly + closure ratifies) |
| HEAVY-band cadence working hypothesis | 2 | stays 2 (P0.S8 is SMALL-band) |

**Phase 0 commitments banked for closure-audit:**

1. Spec-first review cycle expected at closure: 56 (Phase 0) + 1 (Plan v1) + (+1 if Plan v2) + 1 (closure) per +1-per-artifact convention.
2. Q5 estimate range LOCKED at 4-7 anchors, mid 5. Closure-actual reading triggers band-table disposition.
3. `### Phase-0-catches-wrong-premise` NOT activated (premise verified ON-TARGET via spec stub + production-code grep).
4. Cadence: SMALL-band; v1 only OPTIONAL-Plan-v2 path candidate (5th proof case).

---

## §10. Open invariants for Plan v1 to enumerate

1. **D1 dependency-pin invariant** — `dog-ai-dashboard/package.json` contains `"lru-cache": "^10.x"` (or whatever specific version Plan v1 locks).

2. **D2 ordering invariant** — rate-limit check at `dog-ai-dashboard/middleware.ts` sits AFTER `_safeEqual` validation (line ~75) but BEFORE the `NextResponse.next()` pass-through (line ~80). Source-inspection test asserts the ordering.

3. **D2 cache-key invariant** — rate-limit cache key = cookie value (== `.dashboard_token` after validation). Source-inspection test asserts `cookieValue` is the cache key.

4. **D3 response-shape invariant** — 429 response includes `Retry-After` header + JSON error body. Source-inspection test asserts both substrings.

5. **D4 behavioral validation (if testable)** — bombard a test endpoint with 61+ requests in 60s; assert 60 pass + 61st returns 429.

6. **No-side-effect-in-Phase-0 invariant** — this Phase 0 audit landed with zero production code changes.

---

**End of Phase 0 audit.** Ready to forward to auditor.

**Architect's request to auditor:** confirm pre-audit premise + Phase 0 scope decomposition + D1-D4 are the right shape + cadence prediction (SMALL-band v1 only OPTIONAL-Plan-v2 path candidate) is defensible. 4 open questions at §8 await adjudication. Twin-filename pitfall: 11th preventive instance (clean disambiguation against zero pre-existing P0.S8 artifacts).
