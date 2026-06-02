# Dashboard Auth — Edge-Runtime Incompatibility Fix (Developer Spec)

**Filed**: 2026-05-30 · **Architect**: Claude · **Severity**: HIGH (entire dashboard API non-functional behind the auth gate)
**Origin**: Canary finding #1 (pre-P1 canary, 2026-05-30) — user clicked dashboard "reset", got `"Pipeline not started — token not yet generated"`.
**Discipline**: `### Canary-surfaces-real-gaps` + `### Verification-before-completion` (full-suite-run-is-the-proof). This bug existed since P0.S2 shipped and was never caught because P0.S2's tests are source-inspection only and the deferred-canary meant the Edge runtime was never run live. **The fix is NOT done until it is live-verified (§4).**
**Status**: STRUCTURALLY VERIFIED + COMMITTED 2026-06-02 (architect) — **PROVISIONAL, NOT closed.** The parked implementation is complete + spec-conformant; the Python lock layer is green (43 passed / 2 POSIX-skip), the forward-property fail-on-revert is proven, and `tsc --noEmit` is clean (0 errors, after fixing the pre-existing photo `Buffer→BodyInit` drift per user direction). **§4 live-verification remains the actual proof and is the user's run** — per §7, source-inspection (everything done here) is exactly what missed the original bug. See §8.

---

## §1 Root cause (definitive, evidence-backed)

**`dog-ai-dashboard/middleware.ts` uses Node-only APIs that do not exist in the Edge runtime, but Next.js 14 runs middleware in the Edge runtime only.**

Evidence:
- `dog-ai-dashboard/package.json:11` pins **`next: 14.2.5`**. In Next.js 14, middleware runs in the **Edge runtime exclusively** — there is no Node.js middleware runtime (that arrived experimentally in Next 15.2). `dog-ai-dashboard/next.config.js` has no runtime override (and v14 offers none).
- `middleware.ts` calls `fs.readFileSync` (line 67), `Buffer.from` + `crypto.timingSafeEqual` (lines 38-41) — all Node-only, unavailable in Edge.
- At runtime, `fs.readFileSync(_tokenPath())` throws; the catch block (lines 68-77) returns `{error: "Pipeline not started — token not yet generated"}` (401).
- The middleware matcher is `'/api/:path*'` with `/api/auth` allowlisted (lines 60, 140). So **every gated `/api/*` route returns this 401** — all 10 of them. The factory-reset is just the one the user clicked.

What is NOT the problem (ruled out by evidence):
- **Token file**: `faces/.dashboard_token` EXISTS (43 valid chars, readable by the same user). Verified on disk.
- **CWD**: `npm run dev` runs from `dog-ai-dashboard/` (per `scripts/launch.js` — no `cwd` override on the `spawn`), so `process.cwd()/../faces/` correctly resolves to the project-root `faces/`. No stray `faces/` dirs at wrong-CWD candidates.
- **Route handlers**: `app/api/auth/route.ts` is a Route Handler (Node runtime by default), so its identical `fs` code WORKS — that asymmetry (same code, Node context works / Edge context fails) is the tell.
- **factory-reset route handler**: has no token/auth logic of its own (returns only 400/200/500/504), confirming the "token not yet generated" message came from the middleware, before the request reached the handler.

**Conclusion**: the on-disk-token auth model is architecturally incompatible with Next 14 Edge middleware. The token read + cookie compare MUST move to a Node-runtime context (Route Handlers run in Node by default).

---

## §2 Fix design — move the gate into Node-runtime route handlers

**Chosen approach (Option A)**: extract the middleware's auth logic (token read + cookie compare + P0.S8 rate-limit) into a shared Node-runtime helper `lib/requireAuth.ts`, call it at the top of every gated route handler, and remove the broken Edge auth from `middleware.ts`.

Rejected alternatives:
- **Upgrade to Next 15.2 + `runtime: 'nodejs'` middleware**: major version bump (React 19, breaking changes), experimental runtime — disproportionate risk for a single-user localhost dashboard.
- **Edge-safe cookie-presence-only middleware**: still requires the real fs token-compare in each handler (same work as Option A) + adds a redundant layer.

Preserved invariants:
- The distinguishable 401 messages ("token not yet generated" for missing-token vs "Unauthorized" for bad/absent cookie) — P0.S2 D2 lock.
- The constant-time compare (length pre-check + `timingSafeEqual`) — P0.S2 D2 test 8 lock.
- The P0.S8 ORDERING INVARIANT: rate-limit AFTER auth (failed-auth requests must NOT populate the rate-limit cache).
- Fresh token read per request (no module-scope token cache) — P0.S2 D4 lock.
- `/api/auth` stays un-gated (it mints the cookie).

---

## §3 Implementation (D1–D5)

### D1 — NEW `dog-ai-dashboard/lib/requireAuth.ts` (create the `lib/` dir)

Node-runtime helper. Returns a `NextResponse` to return on failure (deny), or `null` on success. Moves the middleware's auth + rate-limit verbatim:

```typescript
// dog-ai-dashboard/lib/requireAuth.ts — P0.S2/S8 auth gate, Node-runtime.
//
// Replaces the Edge-incompatible fs/Buffer/crypto auth that was in
// middleware.ts. Next.js 14 runs middleware in the Edge runtime (no fs),
// so the on-disk-token gate must live in Route Handlers (Node runtime).
//
// Usage at the top of every gated /api/* handler:
//   const denied = requireAuth(req); if (denied) return denied
//
// Spec: tests/dashboard_auth_edge_runtime_fix_spec.md (2026-05-30).

import { NextRequest, NextResponse } from 'next/server'
import fs from 'fs'
import path from 'path'
import crypto from 'crypto'
import { LRUCache } from 'lru-cache'

// faces/.dashboard_token relative to the dashboard CWD (dog-ai-dashboard/)
// -> project-root faces/. Resolved at call time (not module load) so manual
// token replacement / corruption recovery is picked up without a restart
// (preserves P0.S2 D4 fresh-read-per-request invariant).
function _tokenPath(): string {
  return path.join(process.cwd(), '..', 'faces', '.dashboard_token')
}

// Constant-time equality, length pre-check first (P0.S2 D2 test 8 lock —
// bare === is a timing-attack surface; timingSafeEqual needs same-length
// buffers, so length-check short-circuits the trivially-wrong case).
function _safeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false
  return crypto.timingSafeEqual(Buffer.from(a, 'utf8'), Buffer.from(b, 'utf8'))
}

// P0.S8 D2 rate-limit cache — moved verbatim from middleware.ts. Module
// scope: shared across all route handlers in the Node process (Node module
// caching). State resets on dashboard restart (acceptable per P0.S8 Phase 0
// §3.3 — rate-limit state is ephemeral by design).
const _rateLimitCache = new LRUCache<string, number[]>({ max: 100, ttl: 60_000 })

export function requireAuth(req: NextRequest): NextResponse | null {
  // 1. Read token fresh (Node runtime — fs works in Route Handlers).
  //    ENOENT/EACCES -> distinguishable 401 (pipeline not booted / token gone).
  let fileToken: string
  try {
    fileToken = fs.readFileSync(_tokenPath(), 'utf8').replace(/[\r\n]+$/, '')
  } catch {
    return NextResponse.json(
      { error: 'Pipeline not started — token not yet generated' },
      { status: 401 }
    )
  }

  // 2. Cookie present? Absent -> 401 Unauthorized (distinct from missing-token).
  const cookieValue = req.cookies.get('dogai_session')?.value
  if (!cookieValue) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  // 3. Constant-time compare. Mismatch -> 401.
  if (!_safeEqual(cookieValue, fileToken)) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  // 4. P0.S8 ORDERING INVARIANT: rate-limit AFTER auth — failed-auth requests
  //    (returned above) do NOT populate the cache / consume the budget.
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
      { status: 429, headers: { 'Retry-After': String(retryAfterSecs) } }
    )
  }
  recent.push(now)
  _rateLimitCache.set(cookieValue, recent)

  // Authenticated + within rate limit.
  return null
}
```

### D2 — Wire `requireAuth` into all 10 gated route handlers

At the TOP of each exported handler, before any other logic:
```typescript
import { requireAuth } from '@/lib/requireAuth'   // or relative '../../../lib/requireAuth'
// ...
export async function GET(req: NextRequest) {
  const denied = requireAuth(req); if (denied) return denied
  // ... existing logic
}
```

**Per-route checklist** (verify the import path; check the existing `NextRequest` import):

| Route file | Handler(s) | Note |
|---|---|---|
| `app/api/status/route.ts` | `GET()` | **add `(req: NextRequest)`** — currently no param; import NextRequest |
| `app/api/best-friend/route.ts` | `GET()` | **add `(req: NextRequest)`** |
| `app/api/people/route.ts` | `GET()` | **add `(req: NextRequest)`** |
| `app/api/shadow-persons/route.ts` | `GET()` | **add `(req: NextRequest)`** |
| `app/api/enroll/route.ts` | `POST(req: NextRequest)` | already has req |
| `app/api/factory-reset/route.ts` | `POST(req: NextRequest)` | already has req |
| `app/api/photo/route.ts` | `GET(req: NextRequest)` | already has req |
| `app/api/gallery-audit/route.ts` | `GET(_req: NextRequest)` | rename `_req`→`req` (now used) |
| `app/api/people/[id]/route.ts` | `DELETE(...)` | dynamic route; guard the DELETE handler |
| `app/api/gallery-audit/[id]/route.ts` | `GET(...)` + `DELETE(...)` | **BOTH handlers** need the guard |

`/api/auth/route.ts` (GET) — **DO NOT add the guard** (it mints the cookie; stays un-gated, exactly as middleware allowlisted it).

### D3 — Gut `middleware.ts`

Remove the Edge-incompatible auth. Recommended: **delete `dog-ai-dashboard/middleware.ts` entirely** (the matcher + Edge gate are gone; auth is now per-route). The forward-property test in D4 enforces that no gated route is left unguarded.

(If you prefer a belt-and-braces first-line: reduce middleware to an Edge-SAFE cookie-presence check only — `req.cookies.get('dogai_session')` with no fs/Buffer/crypto — returning 401 when absent, else `NextResponse.next()`. This is optional; the real gate is `requireAuth`. Do NOT keep any fs/Buffer/crypto in the middleware.)

### D4 — Rework the tests

`tests/test_dashboard_middleware.py` source-inspects the OLD middleware (asserts `_tokenPath`, `fs.readFileSync` in middleware body, `cookies.get('dogai_session')`, the matcher, `export function middleware`). These assertions are now FALSE. Rework:
- **Delete / rewrite** the middleware-structure assertions (D3 test 10/11/12/13/15 + dynamic-id-routes test).
- **NEW `tests/test_dashboard_auth_helper.py`** (or extend the existing file): source-inspect `lib/requireAuth.ts` for the preserved invariants — `_tokenPath` fresh-read, `timingSafeEqual` + length pre-check, the two distinguishable 401 messages, the rate-limit-AFTER-auth ordering (the `_rateLimitCache.set` must appear after the `_safeEqual` check), the 429 + `Retry-After`.
- **NEW forward-property test** (the key one): glob `app/api/**/route.ts`, and for every route EXCEPT `auth`, assert the file source contains a `requireAuth(` call. This is the structural guarantee that replaces the central matcher — a future route that forgets the guard fails CI. (Same discipline as the project's other forward-property invariants.)
- The P0.S8 rate-limit tests that lived against the middleware move to assert the helper.
- **Unchanged**: `test_dashboard_auth_route.py`, `test_dashboard_token*.py`, `test_dashboard_launch_script.py`, `test_dashboard_bind_tripwire.py` (auth route, token gen, launch wrapper, bind invariant are all untouched).

### D5 — (Optional, while in the file) factory-reset stale-legacy cleanup

`app/api/factory-reset/route.ts:29-31,53` deletes `memory.db`, `memory.db-shm/wal`, `memory_vectors/` — legacy LanceDB artifacts from the pre-brain.db era; harmless (try/catch on nonexistent files) but dead. Optional: drop them. NOT required for the fix.

---

## §4 LIVE-VERIFICATION (non-negotiable — this is the entire lesson)

Structural tests are exactly what missed this bug. **The fix is not complete until the dashboard is run and a gated route is exercised live.** Protocol:

1. Start the pipeline (`python pipeline.py`) so `faces/.dashboard_token` + `.dashboard_auth_url` exist.
2. `cd dog-ai-dashboard && npm run dev`. Confirm it compiles with NO Edge-runtime warnings about Node modules (if middleware is deleted, there should be none).
3. **No-cookie request** (fresh browser / curl): `GET http://127.0.0.1:3000/api/status` → expect **401 `{"error":"Unauthorized"}`** (token read succeeds in Node, cookie absent). **Critically: NOT "token not yet generated"** — if you still see that with the token file present, the helper's fs read is failing and the fix is wrong.
4. **Auth**: open the URL in `faces/.dashboard_auth_url` → `/api/auth` validates → sets `dogai_session` cookie → 302 to `/` → `.dashboard_auth_url` is auto-deleted.
5. **Cookied request**: `GET /api/status` (from the dashboard page) → expect **200 + live data**.
6. **Factory reset**: trigger reset from the dashboard (or `POST /api/factory-reset` with `{"confirm":"RESET"}` + cookie) → expect it runs (reset request/result IPC or direct wipe), NOT a 401.
7. **Negative**: `POST /api/factory-reset` with a bad/absent cookie → 401, and reset does NOT happen.

Capture the dashboard terminal output. Done = steps 3–7 all behave as specified.

---

## §5 Scope guards (do NOT)

- Do NOT upgrade Next.js (no 14→15 bump for this fix).
- Do NOT change the token-generation side (`core/dashboard_token.py`) — it's correct; the bug is purely the dashboard read path.
- Do NOT change `app/api/auth/route.ts` (works; un-gated by design) or the `.dashboard_token`/`.dashboard_auth_url` preservation invariant in factory-reset.
- Do NOT leave any `fs`/`Buffer`/`crypto.timingSafeEqual` in `middleware.ts` (that's the bug).
- Do NOT add the guard to `/api/auth`.

---

## §6 Acceptance criteria

- [ ] `lib/requireAuth.ts` exists; preserves the two distinguishable 401s + constant-time compare + rate-limit-after-auth + fresh-read-per-request.
- [ ] All 10 gated route handlers call `requireAuth(req)` at the top (4 had their `GET()` signature widened to `GET(req: NextRequest)`; gallery-audit/[id] has BOTH GET+DELETE guarded). `/api/auth` un-gated.
- [ ] `middleware.ts` has no fs/Buffer/crypto (deleted, or cookie-presence-only Edge-safe).
- [ ] Forward-property test: every `app/api/**/route.ts` except `auth` contains `requireAuth(`. Middleware-structure tests reworked.
- [ ] **Live-verified per §4** — no-cookie → 401 Unauthorized (not "token not yet generated"); auth → cookie → gated route 200; factory-reset works with cookie, 401 without.
- [ ] Full Python suite still green (the dashboard tests changed; everything else unaffected).

---

## §7 Why this was missed (bank at closure)

P0.S2's middleware tests are **source-inspection** (`test_dashboard_middleware.py` reads `middleware.ts` as text and asserts substrings). They proved the code's SHAPE, not its RUNTIME behavior — and the deferred-canary strategy meant the Edge runtime was never run. This is the **`Full-suite-run-is-the-universal-completeness-proof`** lesson (banked Bundle 5) applied to the dashboard: *no static-verification claim (source-inspection) is exhaustive beyond its method's coverage; running it is the proof.* It's also a clean `### Canary-surfaces-real-gaps` instance (canary #1 of the pre-P1 validation). At closure, bank: dashboard-auth-edge-runtime fix + add a note that dashboard route handlers / middleware need a live-run gate, not just source-inspection — TypeScript/Next runtime behavior is invisible to the Python source-inspection tests.

---

**Standing by**: on developer implementation + live-verification, architect closure-audit (grep-verify the helper + the 10 guarded routes + the gutted middleware + the forward-property test) then bank the doctrine instances.

---

## §8 — Structural-verification record (architect, 2026-06-02) — PROVISIONAL

The parked implementation (a prior developer session) is complete; this records the architect's **structural + TypeScript verification and commit**. It is explicitly **NOT a full closure** — §4 live-verification is the gate, and per §7 the source-inspection done here is the exact method that missed the original bug.

### Verified (structural — grep + read + typecheck)
- **D1 `lib/requireAuth.ts`** — matches §3 verbatim: `_tokenPath()` fresh-read at call time (P0.S2 D4), `_safeEqual` length-precheck + `crypto.timingSafeEqual` (P0.S2 D2 test 8), the two distinguishable 401s ("Pipeline not started — token not yet generated" vs "Unauthorized"), the P0.S8 rate-limit **after** the auth check (ORDERING INVARIANT — `_rateLimitCache.set` strictly after `_safeEqual`), 429 + `Retry-After`, returns `NextResponse | null`.
- **D2 — all 10 gated routes** call `requireAuth(req)` at the top: status / best-friend / people / shadow-persons (the 4 widened from `GET()` → `GET(req: NextRequest)`), enroll / factory-reset / photo / gallery-audit, people/[id] (DELETE), gallery-audit/[id] (**both** GET + DELETE). `/api/auth` is **un-gated** (mints the cookie). Grep-confirmed.
- **D3 `middleware.ts` deleted** — `Test-Path` = False. The Edge-incompatible `fs`/`Buffer`/`crypto` is gone.
- **D4 tests** — `test_dashboard_middleware.py` deleted; `test_dashboard_auth_helper.py` added with all P0.S2/S8 invariant checks **plus the forward-property test** (`test_every_gated_route_calls_require_auth`: every `app/api/**/route.ts` except auth has `requireAuth(` with guard-count ≥ handler-count). `test_dashboard_token.py` reworked.

### Layer-2 / Layer-3
- **Layer-2:** dashboard Python lock layer **43 passed / 2 skipped** (the 2 skips are POSIX-only token-mode tests on Windows). Full Python suite unaffected (the dashboard changes were already in the working tree; they commit prod + tests together, so HEAD stays consistent — unlike the #2/#1 latent-failure shape).
- **Layer-3 fail-on-revert:** removed `status/route.ts`'s `requireAuth` guard → `test_every_gated_route_calls_require_auth` fired ("Forward-property FAILED — not fully guarded") → restored net-zero. The structural lock that replaces the deleted central matcher genuinely catches an unguarded route.
- **TypeScript:** `tsc --noEmit` = **0 errors**. The only pre-existing error (`app/api/photo/route.ts` `Buffer<ArrayBufferLike>` → `BodyInit`, P0.S8-deferred, shifted line 22→24 by the requireAuth guard) was fixed **per user direction** by wrapping the Node `Buffer` in a fresh `Uint8Array` (a valid `BufferSource`, same bytes). This is the one production change made this cycle beyond the parked work; it's out of #3's auth scope but unblocks a clean `tsc`/`npm run build`.

### What is NOT proven here (the gate)
- **§4 live-verification — the user's run.** Boot the pipeline (token exists) → `npm run dev` (must compile with no Edge-runtime warnings; `tsc` clean here is a strong signal but `next dev` is the runtime proof) → no-cookie `GET /api/status` → **401 `Unauthorized`** (NOT "token not yet generated" — that would mean the Node `fs` read is still failing) → auth via `.dashboard_auth_url` → cookied `GET /api/status` → **200** → factory-reset works with cookie, 401 without. Only this proves the Edge→Node move actually fixed the runtime bug. On a passing §4 run, the architect banks the `### Canary-surfaces-real-gaps` (#1) + the §7 "dashboard needs a live-run gate, not source-inspection" doctrine instances and flips this Status to CLOSED.
