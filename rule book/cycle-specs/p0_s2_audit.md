# P0.S2 — Dashboard Authentication — Phase 0 Audit

**Spec:** P0.S2 (complete-plan.md:577-587) — Dashboard has zero authentication
**Track:** P0 — Security vulnerabilities
**Mode:** Strict industry-standard (locked 2026-05-19) + deferred-canary (locked 2026-05-20)
**Status before this audit:** `[OPEN]` (still). S2 tripwire (`tests/test_dashboard_bind_tripwire.py`) holds the deferral honest by requiring explicit `--hostname 127.0.0.1` until S2 ships.

---

## 0. Scope and framing — pre-audit hypothesis vs grep evidence

**Pre-audit framing (architect mental model):** "Wrap every API route in a cookie check. Generate a token at first boot. Done."

**Phase 0 grep-verified findings (read against actual production code, not the spec):**

| Surface | File:Line | Current state |
|---|---|---|
| Dashboard launch bind | `dog-ai-dashboard/package.json:6,8` | Both `dev` + `start` scripts ALREADY explicitly bind `127.0.0.1` via `--hostname` flag (P0.0.1 fixed this; S2 tripwire enforces). |
| API routes (no auth check) | `dog-ai-dashboard/app/api/{status,best-friend,people,shadow-persons,enroll,photo,factory-reset,gallery-audit}/route.ts` + `app/api/people/[id]/route.ts` + `app/api/gallery-audit/[id]/route.ts` | **9 route files. ZERO check any auth header / cookie / token.** Every route is reachable by any TCP client that can connect. |
| Privileged operations exposed | `factory-reset/route.ts:69-130` (POST wipes faces.db, brain.db, brain_graph/, photos), `people/[id]/route.ts:9-41` (DELETE shells out to `delete_person.py`), `gallery-audit/[id]/route.ts:42-73` (DELETE shells out to `audit_person.py --repair`), `enroll/route.ts:12-54` (POST starts camera enrollment) | 4 of 9 routes mutate persistent state. All 4 are anonymous-callable today. |
| Read-only PII surfaces | `people/route.ts` (names + photo paths + face/voice counts), `shadow-persons/route.ts` (mentioned-but-not-enrolled names + facts), `status/route.ts` (current_person + visible_people), `best-friend/route.ts` (best friend identity), `photo/route.ts` (raw JPEG bytes — already path-traversal-guarded but not auth-gated) | All leak identity/presence data. Status route in particular is polled by the dashboard every 2s. |
| Token storage on disk | `faces/` directory + `core/db.py::wipe_all()` semantics | `wipe_all()` deletes `faces/state.json`, `faces/*.db*`, `faces/brain_graph/`, all `*.jpg`. **It does NOT delete `faces/.dashboard_token`** today (file doesn't exist yet). Factory-reset interaction is a D-decision. |
| State.json reader | `lib/db.ts:91-102::getState()` | Reads `faces/state.json` synchronously. No auth context. Used by `/api/status`. |
| Pipeline-side token generation | `pipeline.py` boot sequence | **No existing dashboard-token machinery.** Token generation is a fresh introduction. |
| Existing config flags | `core/config.py` | No `DASHBOARD_BIND` flag exists. `DASHBOARD_*` namespace is empty. Fresh introduction. |
| Middleware | `dog-ai-dashboard/middleware.ts` | **Does not exist** (grep returned no files). Next.js 14 App Router middleware would be the canonical home for cookie-gating; today there is no such file. |
| Next.js config | `dog-ai-dashboard/next.config.js:1-6` | Trivial — only sets `images.unoptimized`. No auth wiring. |
| Cross-spec link to P0.S8 | `complete-plan.md:633-636` | P0.S8 (dashboard rate limiting) explicitly `(depends on P0.S2)`. P0.S2 must establish per-token identity that P0.S8 can rate-limit on. |
| Cross-spec link to P0.0.1 | `tests/test_dashboard_bind_tripwire.py:1-213` + CLAUDE.md Session table P0.0.1 closure | The S2 tripwire's failure-message literal `"S2 (dashboard auth + per-install token + cookie-gated routes)"` is the deferral lock. **Shipping S2 means updating the tripwire's allowlist OR the tripwire stays exactly as is** — the dashboard binds 127.0.0.1 by default even post-S2; `DASHBOARD_BIND` opt-in is gated separately. |

**Pre-audit framing held within ~20% of actual scope** — the mental model was right but missed: (a) Next.js App Router has no global middleware today (one must be created), (b) factory-reset interaction with `.dashboard_token` is an explicit D-decision (preserve vs wipe), (c) the per-install token must be available to the Next.js server process AND to the user (one-time URL display), which is a non-trivial UX flow, (d) the dashboard already passes the S2 tripwire's bind-discipline gate, so S2 is ONLY adding auth (not also fixing bind), (e) P0.0 CI scaffold is the precondition that makes the new structural invariants enforceable on every PR.

**No sub-pattern A wrong-premise.** Phase 0 confirms scope ≈ pre-audit hypothesis, with the 5 refinements above. Banking as ON-TARGET instance for `Phase-0-catches-wrong-premise` doctrine track record (NOT a 6th instance — premise was correct; refinements are scope precision, not premise falsification).

---

## 1. Cross-spec impact analysis

### Upstream dependencies (specs that must hold for S2 to be correct)

- **P0.0 (tiered CI scaffold, 2026-05-08 closed)** — fast.yml runs `pytest -m "not slow and not network and not models"` on every push + PR. S2's new structural invariants (token-file mode-0600 check, every-route-cookie-gated check, etc.) ride this lane. Without P0.0, the invariants are advisory.
- **P0.0.1 (S2 tripwire tightening, 2026-05-08 closed)** — explicit `--hostname 127.0.0.1` in package.json is the precondition that makes "default bind localhost" already true. S2 inherits this property; the spec text "Default bind 127.0.0.1" is **already satisfied** by P0.0.1. S2's job is ONLY the `DASHBOARD_BIND` opt-in flag + startup warning (the layer ABOVE 127.0.0.1 default).
- **No upstream conflicts.**

### Downstream dependents (specs that depend on S2)

- **P0.S8 (rate limiting, OPEN)** — depends-on relationship is explicit (`(depends on P0.S2)` in complete-plan.md:635). P0.S8's lru-cache rate limiter keys on the auth token P0.S2 establishes. S2 must surface a way to identify "this request came from token X" for P0.S8 to consume (cookie value or request property).
- **P0.0.1 tripwire** — S2 closure does NOT remove the tripwire. The tripwire tests `package.json` scripts bind 127.0.0.1; S2's `DASHBOARD_BIND` opt-in flag is a runtime env-var override, separate surface. Tripwire stays intact post-S2. (Confirmed by reading `_SCRIPTS_REQUIRING_EXPLICIT_BIND` invariant in the tripwire — it operates on package.json scripts, not on env vars.)
- **No downstream conflicts.**

### Sideways (parallel code paths)

- **`pipeline.py::wipe_all()` semantics** — currently does NOT delete `.dashboard_token` (file doesn't exist yet). When S2 ships, factory-reset must EITHER preserve the token (user keeps dashboard access through resets) OR wipe + regenerate (forces re-onboarding after reset). **D-decision below (D6).** This is the only sideways write that touches the token's lifecycle.
- **Pipeline-side state.json writer** — `pipeline.py` writes `faces/state.json` continuously; dashboard reads it via `/api/status`. State.json contents are not secret per se but they ARE PII (current_person name, visible_people list). After S2, `/api/status` still streams this, but only to authenticated callers. State.json file itself stays world-readable on disk; the API endpoint is the choke point.

### Lifecycle trace (token's birth → mutation → death)

- **Birth:** first dashboard launch after a fresh install. Pipeline OR dashboard's first-request handler generates a cryptographically-random 32-byte token, writes `faces/.dashboard_token` mode 0600. **D-decision below (D1):** which process owns birth — pipeline at boot, or dashboard lazy on first 401?
- **Mutation:** token is never mutated. Rotated only via explicit user action (rotation tool is OUT OF SCOPE for S2 per "Done when" criteria; mention in known-limitations).
- **Consumption:** dashboard middleware reads cookie on every API request; compares to `.dashboard_token` file (or to an in-memory cached value loaded at server boot). **D-decision below (D3):** read-on-each-request (correctness via fs check) vs read-once-at-boot (perf, but stale if rotated).
- **Death:** factory reset is the only event that could delete the token. **D-decision below (D6).** Token persists across process restarts (the whole point — auth survives `pipeline.py` reboots).

---

## 2. D-decisions enumerated

### D1 — Token generation: pipeline boot vs dashboard lazy

**Question:** Who creates `faces/.dashboard_token`?

**Option A (pipeline-owns):** `pipeline.py` boot sequence checks for `faces/.dashboard_token`. If absent, generates `secrets.token_urlsafe(32)`, writes mode 0600, prints the one-time auth URL (`http://127.0.0.1:3000/api/auth?token=<token>`) to stdout. User clicks → cookie set → dashboard accessible.

**Option B (dashboard-owns):** Next.js server, on first request that hits an unauthenticated route, checks for the token file; if absent, generates + writes mode 0600 + responds with a special "first-launch" page showing the user the URL to bookmark.

**Recommendation (lock at Plan v1):** **Option A (pipeline-owns).**

Why:
1. Pipeline boot is the deterministic single-process startup point. Next.js can be launched multiple ways (`npm run dev`, `npm run start`, `next build && next start`), creating multiple "first-request" race-window opportunities.
2. Pipeline already owns every file under `faces/` per the project's directory-ownership convention (CLAUDE.md project structure section); dashboard is a CONSUMER of faces/ via `lib/db.ts` read-only opens. Adding write authority to the dashboard breaks the ownership invariant.
3. Stdout banner on boot is the user-facing affordance the existing `[Cloud] ... [Pipeline] All systems ready. Watching...` line gives — adding a `[Dashboard] First-launch auth URL: ...` line is a natural extension.
4. Mode 0600 is a POSIX semantic; on Windows it maps to ACL deny-all-but-owner. Python `os.chmod(path, 0o600)` works on both. Next.js's Node.js fs.chmod has the same behavior, so neither option is OS-blocked.

**Edit site:** `pipeline.py` early in `run()`, before any await — call `_ensure_dashboard_token()` helper module-level in pipeline.py OR in a new `core/dashboard_token.py`. **Sub-decision:** module placement deferred to Plan v1 §X.

**Invariants established:**
- File exists at `faces/.dashboard_token` with mode 0600 after first pipeline boot.
- Token is `secrets.token_urlsafe(32)` (43-character URL-safe string, ~256 bits of entropy).
- Token survives pipeline restart (file persistence).
- Token is NOT logged to terminal_output.md (printed to stdout banner only; banner line is grep-filterable by `[Dashboard]` prefix if log redaction needed later).

**Invariants preserved:**
- `faces/` directory is owned by pipeline.py (no new dashboard-side writers).
- Pipeline boot does not block on the dashboard (token generation is local file I/O, sub-millisecond).

**Invariants NOT touched:**
- Token rotation, multi-token (one per device), audit logging of token use — all deferred.

---

### D2 — `/api/auth` endpoint: token → cookie exchange

**Question:** What does the auth endpoint accept, validate, and set?

**Spec text:** "`/api/auth` accepts token via URL parameter on first launch; sets HttpOnly cookie."

**Locked design (precision items at Plan v1):**

- **Route:** `dog-ai-dashboard/app/api/auth/route.ts` (NEW file).
- **Method:** GET (per spec — token comes via URL parameter).
- **Input:** `?token=<value>` query param.
- **Validation:**
  1. Read `faces/.dashboard_token` (absolute path from `process.cwd() + '/../faces/.dashboard_token'`, mirroring existing routes).
  2. If file missing → 503 `{error: "Pipeline not started — token not yet generated"}`.
  3. If query token missing → 400 `{error: "Token required"}`.
  4. **Constant-time string compare** between query token and file token (`crypto.timingSafeEqual(Buffer.from(queryToken), Buffer.from(fileToken))`). Variable-time `===` is a textbook timing-attack vector — flagged in pre-mortem §3.6.
  5. Length-mismatch check BEFORE `timingSafeEqual` (Node throws on mismatched lengths) — if lengths differ, fail-closed 401 without invoking the cmp.
- **Output (success):** 302 redirect to `/` + `Set-Cookie: dogai_session=<token-value>; HttpOnly; SameSite=Strict; Secure=false; Path=/; Max-Age=315360000` (10 years — token persists; rotation is a future feature).
- **Output (failure):** 401 `{error: "Invalid token"}`. **No information leakage** — same error for missing token, wrong token, file-not-found-by-mistake. Internal logging distinguishes; user response uniform.
- **`Secure=false`** because we bind to `127.0.0.1` over HTTP. If `DASHBOARD_BIND` opt-in flag is set to anything non-localhost in the future (post-S2 + post-TLS work), `Secure=true` becomes mandatory; left as a P0.S2.X follow-up.

**Edit site:** new file `dog-ai-dashboard/app/api/auth/route.ts`.

**Invariants established:**
- Cookie name `dogai_session` is the canonical session marker (consumed by every other route's middleware).
- Cookie value EQUALS the file token (no JWT, no symmetric encryption, no derivation — keeps S2 minimal; can layer derivation in S2.X if needed).
- Token-validation uses constant-time compare.

**Invariants preserved:**
- Existing routes continue to work without modification once middleware lands (D4).

**Invariants NOT touched:**
- Multi-user, multi-token, OAuth, password — explicitly out of S2 scope.

---

### D3 — Cookie validation: middleware vs per-route

**Question:** Where does each API route check the cookie?

**Option A (Next.js middleware):** Single `dog-ai-dashboard/middleware.ts` at the dashboard root. Next.js 14 App Router runs middleware on every request matching the `matcher` config; for our case `matcher: ['/api/:path*']` covers all 9 routes. Middleware reads cookie, validates against token file, calls `NextResponse.next()` on success or returns `NextResponse.json({error: "Unauthorized"}, {status: 401})` on failure.

**Option B (per-route helper):** Helper function `requireAuth(req)` called at the top of each route handler. 9 routes × 1 line each.

**Recommendation:** **Option A (middleware).**

Why:
1. **Coverage invariant becomes structural.** With per-route helpers, "did the developer remember to add the line?" is an enforcement gap. A new API route shipping in P0.S8 (rate limiting) or a future feature could land without the check. With middleware + `matcher: ['/api/:path*']`, EVERY new route under `/api/` is automatically gated.
2. **Token file read happens once per request** in either option. No perf delta.
3. **Single edit site** for the auth logic — easier audit, easier rotation later.
4. **Next.js convention** — middleware is the documented App Router idiom for cross-cutting auth.

**Edit site:** new file `dog-ai-dashboard/middleware.ts` at the dashboard root (sibling to `next.config.js`, NOT inside `app/`).

**Matcher exception:** `/api/auth` route MUST be exempt from the cookie check (it's the route that ESTABLISHES the cookie). Two ways to handle:
- (a) Matcher excludes `/api/auth`: `matcher: ['/((?!api/auth).*)']` — explicit regex exclude.
- (b) Middleware allowlists `/api/auth` inline: `if (req.nextUrl.pathname === '/api/auth') return NextResponse.next()`.

**Recommendation:** Option (b) — inline allowlist. Easier to grep ("which routes are exempt from auth?" → one file, one if-statement) and matcher regex is one of the more error-prone Next.js features.

**Invariants established:**
- Middleware file exists at `dog-ai-dashboard/middleware.ts`.
- Middleware reads `dogai_session` cookie, validates against `.dashboard_token` file, returns 401 on any failure.
- `/api/auth` is the ONLY exempt path.
- Static page routes (`/`, `/people`, `/enroll`) are exempt by default — they don't expose data, they only render React shells; the data fetching happens via `/api/*` calls which ARE gated. (Confirm in Plan v1 by reading the 3 page.tsx files — already done in this Phase 0; all 3 use client-side `fetch('/api/X')` calls, so blocking `/api/*` is sufficient.)

**Invariants preserved:**
- Existing route file contents unchanged (zero touches to the 9 route.ts files). Only the new middleware file gates them.

**Invariants NOT touched:**
- Page-route auth (static pages render anonymously, then fetch fails 401, then client redirects to `/api/auth?token=…` flow — flow design is part of Plan v1 D-decision).

---

### D4 — Dashboard read of token file: read-on-each-request vs cached

**Question:** Does the middleware read `.dashboard_token` from disk on EVERY request, or cache it in-memory at boot?

**Option A (read-each-request):** Open file, read, compare, close. Adds ~0.1ms per request (Linux page cache hot).

**Option B (cached-at-boot):** Read once when middleware module loads (Next.js boot), keep in module-scope constant.

**Recommendation:** **Option A (read-each-request).**

Why:
1. **Correctness over micro-perf.** Read-each-request means token rotation (out of scope for S2, but planned for S2.X) Just Works — drop a new value into the file, next request picks it up. Cached-at-boot requires a Next.js restart on rotation, which is hostile to operator ergonomics.
2. **Cost is negligible.** Dashboard request volume is ~0.5 req/s steady-state (status polling every 2s). At 0.1ms per file read, that's 50µs/sec CPU cost — invisible.
3. **Failure mode is cleaner.** If `.dashboard_token` is deleted mid-session (e.g., factory reset), cached-at-boot keeps accepting the stale cookie until restart; read-each-request immediately starts 401-ing. The latter matches user intent.
4. **Page cache makes this effectively a memory read.** Linux caches the file after the first read.

**Edit site:** inside `dog-ai-dashboard/middleware.ts`.

**Invariants established:**
- File is read on every gated request (uncached at the application layer; OS page cache is fine).
- File read errors (ENOENT) → 401, NOT 500. Missing token file = no auth has been set up = unauthorized, NOT internal error.

---

### D5 — `DASHBOARD_BIND` env-var flag

**Question:** How is the LAN-bind opt-in implemented?

**Spec text:** "Default bind `127.0.0.1`. `DASHBOARD_BIND` flag with startup warning if anything else."

**Locked design:**

- **Flag location:** environment variable `DASHBOARD_BIND` read in `dog-ai-dashboard/package.json` scripts via `cross-env` OR via a small Node.js wrapper. **Sub-decision (Plan v1):** cross-env adds a dependency; a wrapper `dog-ai-dashboard/scripts/launch.js` keeps deps clean.
- **Default behavior:** if `DASHBOARD_BIND` unset → use `--hostname 127.0.0.1` (current behavior; tripwire-enforced).
- **Opt-in behavior:** if `DASHBOARD_BIND` set to any value:
  1. Validate it's a valid IP/hostname (regex `^[a-zA-Z0-9.:_-]+$` to prevent shell injection through Next.js argv; reject `*` and `0.0.0.0` with a hard error unless `DASHBOARD_BIND_ALLOW_ANY=1` is ALSO set — double-opt-in for the high-blast-radius case).
  2. Print a multi-line stderr WARNING:
     ```
     ⚠️  DASHBOARD WARNING
     ⚠️  Binding to <value> (non-localhost). Dashboard is reachable from LAN.
     ⚠️  Anyone on your network with the dashboard URL + auth token can:
     ⚠️    - View enrolled people + photos
     ⚠️    - Delete enrolled people
     ⚠️    - Trigger factory reset (wipes all memory)
     ⚠️  Make sure DASHBOARD_BIND is what you want.
     ```
  3. Pass `--hostname <value>` to Next.js.

**Edit site:** `dog-ai-dashboard/scripts/launch.js` (NEW). `package.json` scripts `dev` + `start` change from `next dev --hostname 127.0.0.1 --port 3000` → `node scripts/launch.js dev`.

**S2 tripwire interaction:** The tripwire at `tests/test_dashboard_bind_tripwire.py:106-140` reads `package.json` scripts and asserts `--hostname` is present AND value ∈ `{127.0.0.1, localhost, ::1}`. After S2, `package.json` no longer has `--hostname` literally — it has `node scripts/launch.js dev`. **The tripwire WILL FIRE on the package.json change.** D5's mitigation: update `_SCRIPTS_REQUIRING_EXPLICIT_BIND` OR refactor the tripwire to read `scripts/launch.js`'s default behavior.

**Recommended tripwire refactor (lock at Plan v1):** the tripwire's invariant is "the dashboard binds 127.0.0.1 unless opted-out." Update tripwire to:
- Detect the launch.js wrapper pattern in package.json scripts.
- Read launch.js and assert: (a) default bind is in `_LOCALHOST_HOSTNAMES`, (b) DASHBOARD_BIND env-var path exists AND prints a warning, (c) reject-on-`0.0.0.0`-without-double-opt-in branch exists.
- AST source-inspection of `scripts/launch.js`. Same shape as existing P0.S6 D3.b env-var allowlist invariant — AST scan of source.

**Invariants established:**
- Default bind is 127.0.0.1.
- `DASHBOARD_BIND` env-var is the ONLY way to LAN-expose.
- Setting `DASHBOARD_BIND=0.0.0.0` requires `DASHBOARD_BIND_ALLOW_ANY=1` (double-opt-in).
- Setting `DASHBOARD_BIND` to any non-localhost value prints stderr WARNING.

**Invariants preserved:**
- S2 tripwire invariant ("dashboard binds localhost by default") is preserved via the tripwire refactor — the assertion just lives in a different file.

**Invariants NOT touched:**
- TLS / HTTPS (out of scope; P0.S2.X future).
- Per-LAN-client mTLS (out of scope).

---

### D6 — Factory-reset interaction: preserve vs wipe `.dashboard_token`

**Question:** Does `core.db::wipe_all()` (and the dashboard's mirror in `app/api/factory-reset/route.ts:13-57::wipeAllFiles()`) delete `.dashboard_token`?

**Option A (preserve):** Token survives factory reset. User keeps dashboard access through resets. Faster recovery.

**Option B (wipe + regenerate):** Token is deleted on reset. Pipeline regenerates on next boot. User must re-bookmark new URL OR follow new one-time auth flow.

**Recommendation:** **Option A (preserve).**

Why:
1. **The token is NOT user data.** It's an installation secret, equivalent to an SSH host key or `/etc/machine-id`. Wiping it on factory reset is a category error — factory reset wipes the data the system has LEARNED about the user (faces, conversations, memory), not the system's own provisioning secrets.
2. **UX cost of wipe is non-trivial.** User clicks "factory reset" → dashboard 401s next request → user has to find a terminal, look at pipeline stdout for the new URL, click it. The friction discourages legitimate factory resets.
3. **Security cost of preserve is zero.** The token was already authorized by whoever did the factory reset (otherwise they couldn't have hit the /api/factory-reset endpoint). Preserving it doesn't escalate any privilege.
4. **Symmetry with classifier graph** (per P0.S6 / Spec 1 precedent — `data/classifier_scenarios.db` survives factory reset because it's system intelligence, not personal data). `.dashboard_token` is system provisioning state; same category.

**Edit sites:**
- `core/db.py::wipe_all()` — verify no DELETE of `.dashboard_token` (currently no such delete exists; just add a comment naming the preservation invariant).
- `dog-ai-dashboard/app/api/factory-reset/route.ts:13-57::wipeAllFiles()` — same; verify no delete + add comment.
- **NEW test** in `tests/test_factory_reset_preserves_dashboard_token.py` (or similar) — write a fake `.dashboard_token`, call `wipe_all()` in a tmp_path-redirected setup, assert token survives.

**Invariants established:**
- `.dashboard_token` is in the same preservation tier as `data/classifier_scenarios.db` — system provisioning, not user data.
- Both `wipe_all()` paths (Python and Node.js) explicitly comment the preservation invariant.

**Invariants preserved:**
- Factory reset still wipes everything else under `faces/`.
- The S2 dashboard remains accessible after factory reset (the auth token survives, the wiped data is just gone behind the same auth gate).

---

### D7 — Token file mode 0600 enforcement on creation AND boot-check

**Question:** How do we ensure `.dashboard_token` is mode 0600 across the file's lifetime?

**Concern:** A bug in a future code path could `chmod` the file to 0644. A user could `cp` the file with wrong perms. We need defense-in-depth.

**Locked design:**
- **On creation:** `os.chmod(path, 0o600)` immediately after `open(path, 'w').write(token)`. Atomic-replace via tempfile + os.rename for crash-safety (token write is small but persistent; partial-write protection is cheap).
- **On boot-check:** every pipeline boot, if `.dashboard_token` exists, `os.stat(path)` and verify `st_mode & 0o777 == 0o600`. If not, log a WARNING and re-chmod. This catches drift without requiring perfect creation-time discipline elsewhere.
- **Windows:** `os.chmod` on Windows only supports read-only flag, not POSIX modes. On Windows, additionally apply `icacls <path> /inheritance:r /grant:r "%USERNAME%:F"` via `subprocess.run(...)` — restricts to current user via ACL. **Flag for Plan v1:** verify icacls behavior on user's Windows 11 dev machine; if subprocess.run feels heavy, use `pywin32` or fall back to "warn user that file perms on Windows can't be enforced as strictly as on POSIX."

**Edit site:** new helper `core/dashboard_token.py` with `ensure_token_exists()` and `verify_token_mode()` functions. Pipeline boot calls `ensure_token_exists()` early; the helper itself calls `verify_token_mode()`.

**Invariants established:**
- `.dashboard_token` is mode 0600 (or Windows-equivalent ACL) after every pipeline boot.
- Drift is self-healing (boot-check re-chmods).
- Atomic-replace prevents half-written tokens on crash mid-write.

---

### D8 — Test surface

**Locked test list (Plan v1 will lock counts; Phase 0 forecasts):**

1. **D1 — token generation behavioral:**
   - `test_pipeline_boot_creates_token_if_missing` — tmp `faces/`, call boot helper, assert file exists with 32+ chars of urlsafe content.
   - `test_pipeline_boot_preserves_existing_token` — write a known token, boot, assert unchanged.
   - `test_token_is_high_entropy` — generate 100 tokens, assert no collisions, assert character set is urlsafe alphabet.

2. **D2 — `/api/auth` route behavior** (run as `slow` since Next.js needs to be up; alternatively unit-test the route handler directly via Next.js's `testing` mode):
   - `test_auth_valid_token_sets_cookie_and_redirects` — POST with correct token → 302 + Set-Cookie header present.
   - `test_auth_invalid_token_returns_401` — POST with wrong token → 401.
   - `test_auth_missing_token_returns_400` — POST without `?token` → 400.
   - `test_auth_uses_constant_time_compare` — AST source-inspection of `route.ts` — asserts `timingSafeEqual` is present AND `===` is NOT used for token compare. Same shape as the P0.5 paired-write-methods AST audit.

3. **D3 — middleware coverage invariant:**
   - `test_every_api_route_is_gated_by_middleware` — AST/source scan of `dog-ai-dashboard/app/api/**/route.ts` files + read `middleware.ts` matcher config; assert matcher covers `/api/:path*` AND middleware does NOT have per-route allowlist beyond `/api/auth`. This is the structural invariant that prevents future drift.
   - `test_unauthenticated_request_to_status_returns_401` — behavioral (slow): hit `/api/status` without cookie → 401.
   - `test_authenticated_request_to_status_returns_200` — behavioral (slow): hit `/api/status` with valid cookie → 200 + JSON.

4. **D4 — file read invariant:**
   - `test_middleware_reads_token_file_on_every_request` — source-inspection of middleware.ts; assert no module-level cache constant; assert fs.readFileSync OR fs.readFile is called inside the middleware function body.
   - `test_middleware_returns_401_when_token_file_missing` — behavioral: delete `.dashboard_token` → hit route with any cookie → 401 (not 500).

5. **D5 — bind invariant:**
   - `test_launch_script_default_bind_is_localhost` — read `scripts/launch.js`; assert default value is `127.0.0.1` (or `localhost` / `::1`).
   - `test_launch_script_dashboard_bind_env_overrides` — set DASHBOARD_BIND=192.168.1.5, run launch.js with `--dry-run` flag, assert it would have invoked Next.js with `--hostname 192.168.1.5`.
   - `test_launch_script_rejects_zero_zero_zero_zero_without_double_opt_in` — DASHBOARD_BIND=0.0.0.0 without ALLOW_ANY → process exits non-zero with explicit error.
   - `test_launch_script_prints_warning_on_non_localhost_bind` — DASHBOARD_BIND=192.168.1.5 → stderr contains "DASHBOARD WARNING" + 3+ of the warning lines.
   - **S2 tripwire refactor:** `test_dashboard_package_json_scripts_explicitly_bind_localhost` (existing) — refactor to detect launch.js wrapper pattern instead of literal `--hostname` flag. Same invariant ("default bind is localhost"), different surface.

6. **D6 — factory-reset preservation:**
   - `test_wipe_all_preserves_dashboard_token` — Python side; tmp `faces/`, create token, call `wipe_all()`, assert token still exists with same content + same mode.
   - `test_factory_reset_route_preserves_dashboard_token` — Node.js side; AST source-inspection of `app/api/factory-reset/route.ts::wipeAllFiles`; assert `.dashboard_token` is NOT in the deletion list.

7. **D7 — mode 0600 enforcement:**
   - `test_token_file_mode_is_0600_after_creation` — POSIX-only (skip on Windows); create token via helper, assert `os.stat(path).st_mode & 0o777 == 0o600`.
   - `test_token_file_mode_self_heals_on_boot_check` — POSIX-only; write token + chmod 0644 manually; call boot helper; assert mode back to 0600 + WARNING logged.
   - `test_token_file_windows_acl_restricts_owner` — Windows-only (skip on POSIX); deferred to Plan v1 — exact assertion shape depends on icacls vs pywin32 choice.
   - `test_token_write_is_atomic_replace` — patch `open` to throw mid-write, assert no partial-write file remains.

**Forecast:** **~18-20 tests** across the 7 D-decisions. Plan v1 will lock exact counts. AST-layer structural invariants dominate (cheap, fast, drift-preventing); behavioral tests are slow (need Next.js up) — likely 4-5 of these tagged `@pytest.mark.slow`.

---

## 3. Pre-mortem — failure modes

Required by strict-mode discipline §1. Enumerated 10 failure modes covering the operational, security, and correctness dimensions.

### 3.1 — Token leaks via browser history / shell history

**Failure:** User clicks `http://127.0.0.1:3000/api/auth?token=<token>` from a shared terminal OR a browser that syncs history to other devices. Token appears in `~/.bash_history`, browser history, browser address-bar suggestions, browser extensions reading the URL.

**Mitigation:** D2's `/api/auth` IMMEDIATELY redirects to `/` after setting the cookie; the token URL is only used ONCE. After that, the cookie carries auth. Browser history retains the URL but anyone exploiting it must already have local access (in which case they could read `.dashboard_token` directly). Bash history risk is real but unavoidable for any token-in-URL flow.

**Accepted-with-rationale.** Mention in Plan v1 known-limitations. Future S2.X could move to a CSRF-style flow (POST form on first-launch page) but adds complexity. For a single-user local-dashboard threat model, URL-token is industry-acceptable (matches Jupyter, Grafana initial setup, etc.).

### 3.2 — Token leaks via terminal_output.md archival

**Failure:** Pipeline prints the `[Dashboard] First-launch auth URL: http://127.0.0.1:3000/api/auth?token=XYZ` line to stdout. `terminal_output.md` is opened with `"w"` mode per Session 81 archive hook AND gets renamed to `terminal_output_YYYY-MM-DD_HHMMSS.md` on next boot — so the token sits in a file on disk forever.

**Mitigation:** Redact the token at log time. Either:
- (a) Print the URL to a SEPARATE channel: write `faces/.dashboard_auth_url` mode 0600 once on first boot containing the URL; print to stdout `[Dashboard] First-launch auth URL written to faces/.dashboard_auth_url`. Banner is logged; URL is NOT.
- (b) Print the URL to stdout but exclude it from `terminal_output.md` via redaction in the line-by-line capture layer.

**Recommendation:** Option (a). Simpler, no log-redaction discipline to maintain. **D-decision sub-item — locked in Plan v1.**

### 3.3 — Race window: token file generated but middleware not yet loaded

**Failure:** Pipeline boots first, creates token at T=0. Dashboard `npm run dev` starts at T=5 but Next.js middleware hot-reload runs the middleware module BEFORE the file exists if the user fires up dashboard first. Middleware returns 401 for legitimate first-time auth attempt before the auth flow can complete.

**Mitigation:** D4 (read-each-request) handles this naturally — if file missing on request, return 401 with body `{error: "Pipeline not started"}`. User starts pipeline; next request succeeds. Banking as expected behavior, NOT a bug.

### 3.4 — Cookie SameSite + cross-origin requests

**Failure:** User opens dashboard at `http://127.0.0.1:3000`. A malicious site at `http://attacker.example` makes a `<form action="http://127.0.0.1:3000/api/factory-reset" method="POST">` and tricks the user into submitting. With cookie `SameSite=Strict`, the cookie is NOT sent on the cross-origin request → 401. Without it → wipe.

**Mitigation:** D2 locks `SameSite=Strict`. Cookie is ONLY sent on same-origin requests (i.e., requests originating from the dashboard's own pages). CSRF closed.

**Sub-failure:** Some browsers historically had Strict-mode bypasses. Lax would be more compatible but is CSRF-leaky. Strict is the industry-standard correct choice for this use case.

### 3.5 — JSON-body endpoints accept GET-via-image-tag CSRF

**Failure:** Even with SameSite=Strict, `<img src="http://127.0.0.1:3000/api/factory-reset">` would fire a GET request. If the route accepts GET, factory-reset fires (it doesn't today — only POST — but future routes might).

**Mitigation:** Audit current routes: factory-reset (POST), enroll (POST), people DELETE (DELETE), gallery-audit/[id] DELETE (DELETE) — all use non-GET verbs. Status, people, best-friend, shadow-persons, photo, gallery-audit GET — all read-only. **The destructive-routes-must-be-POST-or-DELETE invariant is implicitly held today; S2 makes it explicit.**

**Structural invariant added:** new test `test_destructive_dashboard_routes_use_non_get_verb` — AST source-scan that any route handler exporting `DELETE` or `POST` is consistent with a destructive operation (whitelist enroll/factory-reset/etc.) AND that no `GET` handler does a write. Plan v1 will lock exact scan shape.

### 3.6 — Timing attack on /api/auth comparison

**Failure:** Attacker on the LAN (assumes user opted into DASHBOARD_BIND non-localhost) can submit candidate tokens and measure response latency to leak the file token byte-by-byte. JavaScript `===` is variable-time on string comparison.

**Mitigation:** D2 locks `crypto.timingSafeEqual()` for the compare. Both inputs MUST be `Buffer` instances of equal length; length-mismatch check before invoking it. Standard Node.js crypto pattern.

### 3.7 — File enumeration via path traversal on /api/photo

**Failure:** Photo route `/api/photo?path=...` already has path-traversal protection (`path.resolve` + `startsWith(facesDir)` check at route.ts:10-14). This is unchanged by S2. But anonymous read access today means an attacker can ENUMERATE existing photo paths even without auth.

**Mitigation:** S2's middleware gates `/api/photo` along with all other `/api/*` routes. Photo path leakage closes naturally.

### 3.8 — `node scripts/launch.js dev` works on Windows + macOS + Linux

**Failure:** Path separators, cross-env behavior, child_process.spawn argument handling differ across platforms. Launch script could be subtly broken on Windows (where the user runs the dashboard).

**Mitigation:** Plan v1 tests `launch.js` with platform-conditional assertions OR via `--dry-run` mode that prints what would be invoked. Cross-platform child_process is well-trodden Node.js territory; using `spawn(process.execPath, ['<path-to-next-cli>', 'dev', '--hostname', ...])` is the canonical safe pattern.

### 3.9 — Pipeline crashes BEFORE writing token; dashboard never gets auth

**Failure:** Pipeline boot fails at startup (e.g., missing TOGETHER_API_KEY per P0.S3) BEFORE the token-generation step runs. User installs the system, runs `npm run dev`, hits 401 with "Pipeline not started — token not yet generated", but they don't realize pipeline.py never reached the token-generation step.

**Mitigation:** D1's token-generation step runs VERY EARLY in pipeline.py `run()`, before async setup, before API-key validation. Specifically, BEFORE `_validate_env()` (P0.S3). Token is local file-write only — no external dependency. Even a pipeline that crashes immediately should have already written the token. **Locked in Plan v1 — `_ensure_dashboard_token()` is the very first call in `run()`, no awaits before it.**

### 3.10 — Multi-instance dashboard sharing a `faces/` directory

**Failure:** User runs `npm run dev` AND `npm run start` simultaneously (port collision likely catches this, but) — OR more realistically, two Next.js workers in cluster mode share the same `.dashboard_token`. Both work fine (read-each-request handles this). But if a future feature adds per-token rate limiting (P0.S8), the rate-limit state in worker-A doesn't see worker-B's requests.

**Mitigation:** Out of P0.S2 scope. Plan v1 mentions in known-limitations + flags to P0.S8 spec author. S2 establishes the cookie surface; S8 is responsible for cross-worker state coordination IF it uses a multi-worker deployment (today the dashboard is single-process).

---

## 4. Multi-direction invariant trace

### Forward (downstream consumers of S2's invariants)

- **P0.S8 (rate limiting)** — consumes the `dogai_session` cookie value as a rate-limit key. S2 must guarantee the cookie value is stable per install (== file token). ✓
- **Future P0.S2.X (rotation)** — consumes the read-each-request property. ✓
- **Future P0.S2.X (TLS)** — flips `Secure=true` flag on the cookie when TLS lands. ✓ (no S2 work needed; the flag's current `false` is documented as "because we bind localhost-only over HTTP today; flip when TLS lands").
- **CI gate** — every PR runs the new tests; PRs that drift the invariants (new route without middleware coverage, new write site without preservation) fail. ✓

### Backward (upstream producers writing to surfaces S2 touches)

- **pipeline.py boot sequence** — adds the token-generation step. No existing producer touches this state (no `.dashboard_token` exists today). ✓ No conflict.
- **`core/db.py::wipe_all()`** — explicitly preserves the token per D6. No existing call sites need changes (they don't currently touch `.dashboard_token`). ✓
- **`dog-ai-dashboard/app/api/factory-reset/route.ts::wipeAllFiles()`** — mirrors the Python preservation. No existing call sites need changes. ✓

### Sideways (parallel code paths that could mutate the same state)

- **No other writer to `faces/.dashboard_token`.** Pipeline owns it; dashboard reads it.
- **No other reader of `dogai_session` cookie.** Middleware owns it.
- **Node.js fs.readFile + Python os.chmod + Windows icacls** — three different code paths to the same file's mode bits. Plan v1 must verify they agree (boot-check after creation; cross-platform test matrix).

### Lifecycle

- **T=0 (birth):** Pipeline writes token at `faces/.dashboard_token` mode 0600. URL written to `faces/.dashboard_auth_url` per 3.2.
- **T=1 (consumption start):** User clicks URL → /api/auth → cookie set → all routes accessible.
- **T=N (steady state):** Token file unchanged; cookie unchanged; every request reads file + compares.
- **T=∞ (death):** Token file is NEVER deleted by S2-level code. Factory reset preserves it. Only manual `rm` ends the lifecycle. (Rotation is future work; rotation = write new file content; cookie becomes stale; user re-clicks new URL.)

All 4 axes traced. No gaps.

---

## 5. 11-gate quality checklist

Per strict-mode discipline §4. Each gate marked APPLIES (with status) or N/A (with rationale).

| Gate | Status | Notes |
|---|---|---|
| Correctness — invariants traced 4-axis | ✓ APPLIES | §4 above. |
| Security — new attack surface? privilege escalation? injection? | ✓ APPLIES | Pre-mortem §3.1-3.10 covers 10 failure modes including timing attack, CSRF, path traversal, token leakage. |
| Privacy — tier classification for any new fact/state? audience filtering? | ✓ APPLIES | `.dashboard_token` is a system_only-tier secret. It is not user data per the existing PRIVACY_LEVELS taxonomy (system_only); it's installation provisioning state. Never appears in brain.db / faces.db (it's a file under faces/ but outside the DB tables). Cookie value is system_only-tier — never logged, never appears in extraction. **Add an explicit "do not log dogai_session cookie value" rule** to the dashboard's stdout/log path. |
| Performance — hot-path cost? worst-case latency? memory footprint? | ✓ APPLIES | Per-request: 1 fs.readFile (~0.1ms, page-cache hot) + 1 constant-time compare (~µs). ~0.5 req/s steady state. Memory: 32-byte buffer. All negligible. |
| Observability — log line per D-decision OR explicit no-log justification | ✓ APPLIES | D1: `[Dashboard] Token created at faces/.dashboard_token` (one-time at first boot) + `[Dashboard] Auth URL written to faces/.dashboard_auth_url` (one-time). D2 401s: dashboard server log "[Auth] Invalid token attempt from <ip>" (NO token value logged). D5: stderr warning block. D7: "[Dashboard] Token mode self-healed from 0644 to 0600" (only on drift). |
| Test pyramid — unit + AST + behavioral + (E2E if applicable) per D-decision | ✓ APPLIES | §2.D8 forecasts 18-20 tests across the 7 D-decisions. Mix of AST source-inspection (D2 timingSafeEqual, D3 middleware matcher, D5 launch.js shape, D6 preservation) + behavioral (D1 token creation, D3 401/200, D4 missing file, D7 self-heal) + structural (D3 every-route-coverage invariant). |
| Regression guards — at least one test per D-decision defending the failure mode that motivated the spec | ✓ APPLIES | The motivating failure is "anyone on the network reaching /api/factory-reset wipes the system." Test: `test_unauthenticated_request_to_factory_reset_returns_401` (locked in Plan v1). Each D-decision has its own defense; the global motivation is covered by D3.test 2. |
| Pre-mortem — 5+ failure modes listed + mitigated or accepted-with-rationale | ✓ APPLIES | §3 lists 10. |
| Multi-direction trace — forward/backward/sideways/lifecycle all named | ✓ APPLIES | §4. |
| Backward compat — identified breaking changes + migration path | ✓ APPLIES | **Breaking change:** existing dashboard users who have the URL bookmarked at `http://127.0.0.1:3000/` will get 401 after S2 ships. Migration: pipeline prints the one-time auth URL to stdout on next boot; user clicks once, cookie persists. Documented in Plan v1 known-limitations. Local-only user (Jagan) — single user — migration is "click the URL once." Acceptable. **Tripwire refactor** (D5) is a structural breaking change to the existing tripwire test; locked. |
| Doc updates — CLAUDE.md / complete-plan.md / memory files queued | ✓ APPLIES | CLAUDE.md Session table entry. complete-plan.md P0.S2 flip `[OPEN]` → `[~]` (in-flight) → closed status. `to_be_checked.md` entry at closure (deferred-canary discipline). No memory file changes anticipated — strict-mode + deferred-canary disciplines already cover the meta-rules. |

All 11 gates APPLY — no N/A. S2 is a multi-surface security spec; nothing is out-of-scope at the gate level.

---

## 6. Deferred-canary `to_be_checked.md` plan

Per the deferred-canary strategy locked 2026-05-20: no live canary fires for S2. At closure, an entry is added to `c:\Users\jagan\dog-ai\to_be_checked.md` capturing the validation checklist for the end-of-P0.R11 canary week.

**Planned `to_be_checked.md` entry (forecast — locked at closure):**

```
## P0.S2 — Dashboard authentication (closed YYYY-MM-DD)

Surfaces shipped:
- core/dashboard_token.py (NEW): _ensure_token_exists, _verify_token_mode
- pipeline.py: _ensure_dashboard_token() call early in run()
- core/db.py::wipe_all(): explicit preservation comment for .dashboard_token
- dog-ai-dashboard/middleware.ts (NEW): cookie-gated /api/* matcher
- dog-ai-dashboard/app/api/auth/route.ts (NEW): GET /api/auth?token=X → cookie
- dog-ai-dashboard/app/api/factory-reset/route.ts: explicit preservation
- dog-ai-dashboard/scripts/launch.js (NEW): DASHBOARD_BIND env wrapper
- dog-ai-dashboard/package.json: scripts changed to `node scripts/launch.js dev|start`
- tests/test_dashboard_bind_tripwire.py: refactored to detect launch.js wrapper

PASS signals (canary log should show):
- [Dashboard] Token created at faces/.dashboard_token (first boot only)
- [Dashboard] Auth URL written to faces/.dashboard_auth_url
- Browser: clicking the auth URL redirects to / and dashboard loads
- All API routes return 200 once cookie is set
- After factory reset: dashboard STILL accessible (token preserved)
- DASHBOARD_BIND unset: launch.js binds 127.0.0.1
- DASHBOARD_BIND=192.168.1.5: stderr WARNING + bind succeeds

FAIL signals:
- Anonymous /api/factory-reset succeeds (cookie check bypassed)
- /api/status returns data without cookie
- Token URL appears verbatim in terminal_output*.md
- DASHBOARD_BIND=0.0.0.0 without ALLOW_ANY succeeds (no error)

Test scenario:
1. Fresh install, no .dashboard_token
2. Start pipeline → verify token + URL files created mode 0600
3. Open dashboard at 127.0.0.1:3000 → expect 401 (no cookie)
4. Click auth URL → expect redirect to / and dashboard loads
5. Refresh dashboard → status loads (cookie persistent)
6. Trigger factory reset → wait for completion → refresh → dashboard STILL works (token survived)
7. Stop pipeline, set DASHBOARD_BIND=192.168.0.50, start → expect WARNING on stderr
8. Stop pipeline, set DASHBOARD_BIND=0.0.0.0 → expect hard error
9. Stop pipeline, set DASHBOARD_BIND=0.0.0.0 + DASHBOARD_BIND_ALLOW_ANY=1 → expect WARNING + bind succeeds

Dependencies on other specs:
- Composes with P0.S8 (rate limiting) when that ships — cookie value = rate-limit key

Known limitations (banked accepted-with-rationale):
- Single-user multi-token not supported (deferred to S2.X)
- TLS not enforced (Secure=false on cookie because localhost+HTTP; flip on TLS ship)
- Token-in-URL bookmark leakage on shared terminals (industry-standard Jupyter-style trade-off)
- Token rotation not automated (manual via rm + restart; deferred to S2.X)
```

---

## 7. Scope-expansion check

Per discipline `### Phase-0-catches-scope-expansion` (informal observation, 1 instance at P0.S7.D-C). Pre-audit assumed: "wrap every route in auth check." Phase 0 grep-confirmed scope ≈ pre-audit, with 5 refinements (no global middleware exists today, factory-reset interaction, token UX flow, S2 tripwire refactor, P0.0 CI prereq).

**Conclusion:** S2 is NOT a scope-expansion-via-Phase-0 instance. Scope held within ~20% of pre-audit hypothesis. The 5 refinements are scope precision, not scope expansion.

**Estimated effort:** 1.5-2 days at the developer layer (Plan v1 will lock — Phase 0 forecast is conservative-precise).

---

## 8. Architect discipline counts (banking at Phase 0 close)

- **Spec-first review cycle for multi-day specs** — 17th application (running count from CLAUDE.md doctrine: 16-for-16 → 17-for-17 once this audit completes and Plan v1 lands).
- **Phase-0-catches-wrong-premise** — NOT incremented (no wrong premise; Phase 0 confirms ON-TARGET). 5 instances stays.
- **Strict-industry-standard mode** — 6th consecutive application (P0.S7.5.1 v1, P0.S7.5.1 v2, P0.S7.5.1 closure, P0.S7.5.2 Phase 0, P0.S7.5.2 v1, P0.S7.5.2 v2, P0.S7.5.2 closure all applied 5/5 gates; this Phase 0 is the next consecutive application AT A NEW SPEC = cross-spec generalization test continuing to PASS — discipline holding across the spec boundary).
- **Deferred-canary strategy** — 2nd application (P0.S7.5.2 closure was the 1st). This Phase 0 plans the `to_be_checked.md` entry upfront rather than treating it as closure overhead — banking as positive evolution of the strategy.
- **Auditor-Q5 estimates trail grep** — N/A at Phase 0 (no auditor estimate to compare yet; will resurface at Plan v1 if auditor's quantitative estimates diverge from grep counts).

---

## 9. Plan v1 forecast

Plan v1 will lock:
- Module placement for `core/dashboard_token.py` (or rejection in favor of inlining in pipeline.py).
- Exact `secrets.token_urlsafe()` byte count (32 → 43 chars; or 24 → 32 chars; locked at Plan v1).
- Windows ACL implementation choice (subprocess+icacls vs pywin32 vs warn-only).
- Exact test counts per D-decision (Phase 0 forecasts ~18-20).
- Cookie attributes precision: `Max-Age` vs `Expires`, exact value, `Path=/` confirmed.
- `scripts/launch.js` cross-platform spawn pattern.
- S2 tripwire refactor details (which assertions move; which stay).

Plan v1 will surface at least 2 architect-anticipated precision items per the running pattern.

---

## 10. Strict-mode operational test (per discipline §10)

- [x] Pre-mortem section exists (§3 — 10 failure modes).
- [x] Multi-direction invariant trace exists (§4 — forward/backward/sideways/lifecycle).
- [x] Quality-gate checklist named (§5 — all 11 gates marked APPLIES).
- [x] Cross-spec impact analysis exists (§1).
- [x] Closure-audit step is scheduled (implicit — will execute per `### Architect-reads-production-code-before-sign-off` discipline at closure).

All 5 strict-mode tests pass at Phase 0. Discipline holds.

---

**End of Phase 0 audit.**

Ready to share with auditor. Standard sequence: this audit → auditor review → Plan v1 with refinements → auditor review → Plan v2 → joint sign-off → developer implementation → closure.
