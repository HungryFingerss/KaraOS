# P0.S2 — Dashboard Authentication — Plan v1

**Predecessor:** `tests/p0_s2_audit.md` (Phase 0)
**Status:** Plan v1 — auditor's 5 precision items addressed + 1 new pre-mortem failure mode + extended test surface
**Mode:** Strict industry-standard + deferred-canary

---

## 1. Precision items from auditor verdict (addressed inline)

### P1 — Route count: 9 → 10

Audit §0 narrative said "9 route files." Glob returns 10. Inline enumeration was actually correct (lists all 10); only the headline number was wrong.

**Locked count (Plan v1):** **10 API route files** under `dog-ai-dashboard/app/api/`:

1. `api/auth/route.ts` — NEW (D2)
2. `api/status/route.ts` — existing
3. `api/best-friend/route.ts` — existing
4. `api/people/route.ts` — existing
5. `api/people/[id]/route.ts` — existing
6. `api/shadow-persons/route.ts` — existing
7. `api/enroll/route.ts` — existing
8. `api/photo/route.ts` — existing
9. `api/factory-reset/route.ts` — existing
10. `api/gallery-audit/route.ts` — existing
11. `api/gallery-audit/[id]/route.ts` — existing

That's actually **11 routes after S2 ships** (10 existing + 1 new `/api/auth`). The Phase 0 audit's "9/10" confusion stemmed from miscounting the existing routes (10) and not adding the new one. **Plan v1 lock: 10 existing + 1 new = 11 total post-ship. 10 are middleware-gated. 1 (`/api/auth`) is allowlisted.**

The "every API route is gated" structural invariant (D3 test 1) now reads as "every route under `app/api/` EXCEPT `app/api/auth/` is reachable only with a valid `dogai_session` cookie."

### P2 — Dynamic-route middleware coverage

Next.js matcher `/api/:path*` syntax is correct for runtime URL matching (Next.js parses request URLs against it), NOT file-system glob syntax. But coverage of `[id]` segments is worth a behavioral test because a future maintainer reading the matcher config might assume static-only.

**Added to test surface (D3 — was 3 tests, now 4):**

- `test_middleware_gates_dynamic_id_routes` — behavioral (slow). Start Next.js, hit `/api/people/jagan_001` AND `/api/gallery-audit/some_id` WITHOUT cookie. Assert both return 401. Document this is the "dynamic-route invariant guard" — a future routing refactor that breaks matcher coverage on `[id]` segments will fail this test.

### P3 — Windows ACL: locked to subprocess+icacls

Phase 0 listed 3 options. Plan v1 picks one based on the bench result.

**Bench (run 2026-05-20 on user's Windows 11 dev machine):**

```python
import subprocess, getpass, tempfile, os
with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
    f.write('token'); p = f.name
# Default ACL (leak surface):
#   CodexSandboxUsers:(I)(M,DC), some-SID:(I)(M,DC), SYSTEM:(I)(F),
#   Administrators:(I)(F), jagan:(I)(F)
r = subprocess.run(['icacls', p, '/inheritance:r', '/grant:r', f'{getpass.getuser()}:F'],
                   check=False, capture_output=True, text=True)
# r.returncode == 0
# AFTER: ACERJN\jagan:(F) — only user has Full Control
# Re-run on already-restricted file: RC=0, idempotent
```

**Locked design:**

```python
# core/dashboard_token.py
def _apply_windows_acl(path: str) -> bool:
    """Restrict path to current user only via icacls. Returns True on success.
    Best-effort: returns False + logs WARNING if icacls fails or is unavailable.
    """
    import getpass, subprocess
    try:
        username = getpass.getuser()
        result = subprocess.run(
            ['icacls', path, '/inheritance:r', '/grant:r', f'{username}:F'],
            check=False,
            capture_output=True,
            text=True,
            timeout=5.0,  # icacls should never take this long; bail on hang
        )
        if result.returncode == 0:
            return True
        # icacls failed — log full output, do NOT crash
        print(
            f"[Dashboard] WARNING: icacls failed to restrict {path!r} "
            f"(rc={result.returncode}); file may be readable by other Windows accounts. "
            f"stdout: {result.stdout.strip()!r}, stderr: {result.stderr.strip()!r}",
            flush=True,
        )
        return False
    except FileNotFoundError:
        # icacls.exe not in PATH — Windows installation missing System32 entries
        print(
            f"[Dashboard] WARNING: icacls not found on PATH; cannot restrict "
            f"{path!r} on Windows. Token file is mode 0600 (Python chmod) but "
            f"other Windows accounts may still have inherited permissions.",
            flush=True,
        )
        return False
    except subprocess.TimeoutExpired:
        print(f"[Dashboard] WARNING: icacls timed out restricting {path!r}", flush=True)
        return False
```

**Cross-platform helper that calls the right path:**

```python
def _restrict_to_owner(path: str) -> None:
    """Apply 0600-equivalent restriction. POSIX uses chmod; Windows uses icacls."""
    import os, sys
    os.chmod(path, 0o600)  # POSIX: real effect. Windows: read-only flag only.
    if sys.platform == "win32":
        _apply_windows_acl(path)
```

**Rationale per auditor's P3:**
- (a) zero new pip dependency — icacls is in System32
- (b) subprocess+icacls is the documented Windows path-permission idiom
- (c) Windows 11 ships icacls; bench confirms it's on PATH (`subprocess.run` resolves it)
- (d) `check=False` + return-code inspect avoids surprise crashes on quirks
- (e) WARNING log is the right escape hatch when security boundary can't be enforced — surfaces honestly rather than silent-fail
- (f) `timeout=5.0` guards against icacls hangs (a class of bug we haven't seen but is cheap to prevent)

**Fallback policy:** if icacls fails, we LOG and CONTINUE. We do NOT crash the pipeline. The `chmod(0o600)` already ran (sets the read-only attribute on Windows, which is weaker than ACL restriction but non-zero protection). The user is told the limitation via the WARNING. This matches the auditor's "best-effort restrict + warn user" recommendation.

### P4 — `.dashboard_auth_url` one-shot delete

Audit §3.2 locked: write the auth URL to `faces/.dashboard_auth_url` mode 0600 instead of printing to stdout (which would persist in `terminal_output_*.md` archives).

Auditor's P4 concern: the URL file is itself a token-carrying artifact. If user shares `faces/` contents for debugging (GitHub issue, Discord screenshot), URL leaks.

**Locked design:**

1. Pipeline boot: if `.dashboard_token` doesn't exist, generate it. ALSO generate `.dashboard_auth_url` with content `http://127.0.0.1:3000/api/auth?token=<token>` mode 0600.
2. Stdout banner: `[Dashboard] First-launch auth URL written to faces/.dashboard_auth_url — click once, then delete this file (auto-deleted after first successful auth)`
3. `/api/auth` route on successful token validation:
   - Set cookie (existing D2 behavior)
   - Delete `faces/.dashboard_auth_url` if it exists (best-effort; ignore ENOENT)
   - Redirect to `/`
4. If `.dashboard_auth_url` is missing on subsequent boots (auth already happened), pipeline does NOT regenerate. Token file remains the auth source-of-truth.

**Implementation site:** in `dog-ai-dashboard/app/api/auth/route.ts`, after the constant-time compare succeeds but BEFORE setting the cookie, `fs.unlinkSync(authUrlPath); // ignore ENOENT` wrapped in try/catch.

**Regression test added (D2 — was 4 tests, now 5):**

- `test_auth_success_deletes_auth_url_file` — write `.dashboard_token` AND `.dashboard_auth_url` to a tmp `faces/`, hit `/api/auth?token=<correct>`, assert: cookie set, `.dashboard_auth_url` no longer exists, `.dashboard_token` still exists. Behavioral (slow).
- `test_auth_failure_does_not_delete_auth_url_file` — submit wrong token, assert `.dashboard_auth_url` still exists. (Wrong attempts don't burn the URL.)

**Invariant established:**
- `.dashboard_auth_url` is one-shot: lifetime = first-boot → first-successful-auth. After that, only `.dashboard_token` remains.
- Sharing `faces/` after first auth no longer leaks the auth URL.

**Pre-mortem extension §3.11 (new failure mode):**

- **Failure:** user shares `faces/.dashboard_token` directly instead of the URL file. Token leaks regardless.
- **Mitigation:** Out of scope for S2 — same problem any token-on-disk system has. Plan v1 mentions in known-limitations: "users sharing `faces/` directly leak `.dashboard_token`; this is the fundamental limit of file-based provisioning. Future S2.X could move to OS-keyring storage."

### P5 — GET vs POST for `/api/auth`

Audit locked GET per spec text ("URL parameter on first launch"). Auditor's P5 concern: GET URLs land in web-server access logs, reverse-proxy logs, browser referrer chains.

**Locked design:** Stay with GET for S2. Reasoning:

1. Single-user localhost-only deployment today: no reverse proxy, no shared web server, no access log retention.
2. UX cost of POST: would require an HTML form with a submit button instead of a clickable URL. Adds a page (`/api/auth/landing` or similar) just for the form. Non-trivial scope creep.
3. Browser referrer: HttpOnly cookie is set on the same-origin redirect (302), the URL with token is in the navigation history of the user's browser ONLY (no external referrer). Mitigated by D2's IMMEDIATE 302 to `/`.
4. The URL is single-use (P4): `.dashboard_auth_url` is deleted after first auth, so even a leaked URL is a leaked stale token (still bad — token doesn't auto-rotate — but the convenience artifact is gone).

**Banked in Plan v1 known-limitations (verbatim for closure narrative):**

> S2 uses GET for `/api/auth?token=X` per the spec's "URL parameter on first launch" framing. This is acceptable for localhost-only single-user deployment. If a future migration adds TLS + reverse proxy (P0.S2.X), or if dashboard request lines are logged anywhere upstream of the dashboard process, the token will appear in those logs verbatim. **Forward-tracked S2.X follow-up:** flip `/api/auth` to POST-with-form-body; add a static landing page at `/auth` that POSTs the form. Defer until TLS/proxy migration creates the actual logging surface.

This is a NAMED RISK with an explicit follow-up trigger condition. Not a silent acceptance.

---

## 2. Test surface — locked counts (Plan v1)

Phase 0 forecast 18-20 tests. Auditor estimate 16-22. After P2 + P4 additions and an explicit D3 test split:

### D1 — token generation (4 tests)

1. `test_pipeline_boot_creates_token_if_missing` — POSIX: tmp `faces/`, call `_ensure_dashboard_token()`, assert file exists, length 43 (token_urlsafe(32) → 43 chars), readable mode 0600.
2. `test_pipeline_boot_preserves_existing_token` — write known token, boot, assert unchanged.
3. `test_token_is_high_entropy` — generate 100 tokens, assert no collisions, assert chars in `[A-Za-z0-9_-]` urlsafe alphabet.
4. `test_token_creation_is_atomic_replace` — monkeypatch `open` to throw mid-write; assert no partial-write file remains AND no `.tmp` artifact.

### D2 — `/api/auth` route (5 tests)

5. `test_auth_valid_token_sets_cookie_and_redirects` — behavioral (slow): GET `/api/auth?token=<correct>` → 302 + `Set-Cookie: dogai_session=...; HttpOnly; SameSite=Strict; Path=/`.
6. `test_auth_invalid_token_returns_401` — GET `?token=<wrong>` → 401 + no Set-Cookie.
7. `test_auth_missing_token_returns_400` — GET without `?token` → 400 + no Set-Cookie.
8. `test_auth_uses_constant_time_compare` — AST source-inspection of `route.ts`; assert `timingSafeEqual` is present + literal `===` is NOT used to compare token values + length-equality check precedes timingSafeEqual.
9. `test_auth_success_deletes_auth_url_file` (NEW per P4) — write `.dashboard_token` AND `.dashboard_auth_url`, valid auth → `.dashboard_auth_url` deleted, `.dashboard_token` remains. Behavioral.

### D3 — middleware coverage (5 tests)

10. `test_every_api_route_is_gated_by_middleware` — structural: glob `dog-ai-dashboard/app/api/**/route.ts`, build set of route paths; read middleware.ts matcher + inline allowlist; assert (set of gated routes) == (set of all routes) - {`/api/auth`}.
11. `test_unauthenticated_request_to_status_returns_401` — behavioral.
12. `test_authenticated_request_to_status_returns_200` — behavioral; with valid cookie → JSON body.
13. `test_unauthenticated_request_to_factory_reset_returns_401` — behavioral; the regression-guard for the motivating failure ("anonymous attacker can wipe the system").
14. `test_middleware_gates_dynamic_id_routes` (NEW per P2) — behavioral; hit `/api/people/jagan_001` and `/api/gallery-audit/some_id` WITHOUT cookie → both 401. Dynamic-segment coverage invariant.

### D4 — file read invariant (2 tests)

15. `test_middleware_reads_token_file_on_every_request` — AST source-inspection of `middleware.ts`; assert no module-scope `const TOKEN = fs.readFileSync(...)` cache; assert `fs.readFileSync` OR equivalent inside the middleware function body.
16. `test_middleware_returns_401_when_token_file_missing` — behavioral; delete `.dashboard_token`, hit any gated route → 401 (not 500).

### D5 — bind invariant + S2 tripwire refactor (5 tests)

17. `test_launch_script_default_bind_is_localhost` — AST/source scan of `scripts/launch.js`; assert default value is in `{'127.0.0.1', 'localhost', '::1'}`.
18. `test_launch_script_dashboard_bind_env_overrides` — set DASHBOARD_BIND=192.168.1.5, run launch.js `--dry-run`, stdout includes `--hostname 192.168.1.5`.
19. `test_launch_script_rejects_0_0_0_0_without_double_opt_in` — DASHBOARD_BIND=0.0.0.0 without ALLOW_ANY → process exit non-zero + stderr contains explanation.
20. `test_launch_script_prints_warning_on_non_localhost_bind` — DASHBOARD_BIND=192.168.1.5 → stderr contains `"DASHBOARD WARNING"` literal + ≥3 of the 6 warning lines.
21. `test_dashboard_bind_tripwire_refactor` — REFACTOR of existing `test_dashboard_package_json_scripts_explicitly_bind_localhost` (`tests/test_dashboard_bind_tripwire.py:83-140`). New invariant: package.json `dev` + `start` scripts MUST invoke `node scripts/launch.js dev|start`; launch.js source MUST have default-bind in `{'127.0.0.1', 'localhost', '::1'}`; launch.js MUST have a `DASHBOARD_BIND` env-var check branch. Same invariant ("default bind localhost; opt-out requires explicit env-var"); new surface.

### D6 — factory-reset preservation (3 tests)

22. `test_wipe_all_preserves_dashboard_token` — Python side; tmp `faces/`, create `.dashboard_token` + dummy `faces.db`, call `core.db.wipe_all()`, assert `.dashboard_token` exists unchanged + `faces.db` is deleted.
23. `test_factory_reset_route_preserves_dashboard_token` — AST source-inspection of `app/api/factory-reset/route.ts::wipeAllFiles`; assert `.dashboard_token` is NOT in the deletion list literal AND a comment string referencing P0.S2 preservation exists.
24. `test_auth_failure_does_not_delete_auth_url_file` (NEW per P4) — wrong token submitted; assert `.dashboard_auth_url` still exists after the failed auth attempt.

### D7 — mode + ACL enforcement (4 tests)

25. `test_token_file_mode_is_0600_after_creation` — POSIX-only (skip on Windows); create via helper, assert `os.stat(path).st_mode & 0o777 == 0o600`.
26. `test_token_file_mode_self_heals_on_boot_check` — POSIX-only; write token, manually chmod 0644, call boot helper, assert mode back to 0600 + WARNING log captured.
27. `test_windows_icacls_invocation` (NEW per P3 lock) — Windows-only (skip on POSIX); patch `subprocess.run` to spy on args; call `_apply_windows_acl(tmp_path)`; assert args == `['icacls', tmp_path, '/inheritance:r', '/grant:r', f'{getpass.getuser()}:F']` AND `check=False` + `capture_output=True` + `timeout=5.0`.
28. `test_windows_icacls_failure_logs_warning_returns_false` — Windows-only; patch `subprocess.run` to return `CompletedProcess(returncode=1, stdout='', stderr='access denied')`; call helper; assert returns False + stderr/stdout captured in WARNING log + pipeline does NOT crash.

**Total locked count: 28 tests.** Phase 0 forecast 18-20; ~40% over due to P2 dynamic-route, P3 explicit icacls testing (2 tests), P4 .dashboard_auth_url lifecycle (2 tests), and the existing-test refactor (D5 test 21).

**Within auditor's 16-22 estimate:** slight OVERAGE by 6 tests (28 vs 22 ceiling). Plan v1 explicitly banks this overage as auditor-Q5 6th instance trend continuation — see §10.

---

## 3. Edit-site enumeration (locked)

### Pipeline-side (Python)

| File | Change | Lines (approx) |
|---|---|---|
| `core/dashboard_token.py` | NEW — `_ensure_token_exists()`, `_verify_token_mode()`, `_apply_windows_acl()`, `_restrict_to_owner()`, `_write_auth_url()`, `_atomic_write_secret()` | ~80 LOC new file |
| `pipeline.py::run()` | Call `_ensure_dashboard_token()` BEFORE `_validate_env()` (per pre-mortem §3.9). Module-level import of `core.dashboard_token`. | ~3 lines inserted near top of run() + 1 import |
| `core/db.py::wipe_all()` | Add comment naming preservation invariant + verify `.dashboard_token` and `.dashboard_auth_url` are NOT in the deletion list. (No deletion exists today; comment is the discipline anchor.) | ~5 lines comment |
| `core/config.py` | NEW namespace `DASHBOARD_*` if needed (currently NO config touches the dashboard from Python side; Plan v1 keeps it that way — DASHBOARD_BIND is a Node-side env var read by `scripts/launch.js`, not a Python config). | 0 lines |

### Dashboard-side (TypeScript/JavaScript)

| File | Change | Lines (approx) |
|---|---|---|
| `dog-ai-dashboard/middleware.ts` | NEW | ~40 LOC |
| `dog-ai-dashboard/app/api/auth/route.ts` | NEW | ~50 LOC |
| `dog-ai-dashboard/scripts/launch.js` | NEW | ~70 LOC |
| `dog-ai-dashboard/package.json:5-9` | `scripts.dev` + `scripts.start` change from `next dev --hostname 127.0.0.1 ...` to `node scripts/launch.js dev|start` | 2 lines changed |
| `dog-ai-dashboard/app/api/factory-reset/route.ts:13-30` | Add comment naming P0.S2 preservation invariant for `.dashboard_token` and `.dashboard_auth_url`; no behavior change (deletion list already excludes them) | ~5 lines comment |

### Tests

| File | Change | Tests |
|---|---|---|
| `tests/test_dashboard_token.py` | NEW — D1, D4, D6 Python tests + D7 POSIX tests | ~12 tests |
| `tests/test_dashboard_token_windows.py` | NEW — D7 Windows-only tests (`@pytest.mark.skipif(sys.platform != 'win32')`) | 2 tests |
| `tests/test_dashboard_auth_route.py` | NEW — D2 tests + D6 auth-url-preservation | ~6 tests |
| `tests/test_dashboard_middleware.py` | NEW — D3 + D4 tests | ~6 tests |
| `tests/test_dashboard_bind_tripwire.py` | REFACTOR — existing 4 tests stay; the `test_dashboard_package_json_scripts_explicitly_bind_localhost` body changes per P3 to detect launch.js wrapper | 4 existing (1 refactored) |
| `tests/test_dashboard_launch_script.py` | NEW — D5 launch.js tests | ~4 tests |

**Total new test files: 6. Refactored: 1.** All behavioral tests carry `@pytest.mark.slow` per CLAUDE.md test-tier convention.

---

## 4. Cross-platform discipline

**POSIX (Linux Jetson target):** `os.chmod(0o600)` is authoritative. `_apply_windows_acl()` is a no-op (sys.platform != "win32").

**Windows (dev machine):** `os.chmod(0o600)` sets read-only flag only. `_apply_windows_acl()` runs icacls per the bench. Both are best-effort; if icacls fails the token file remains protected by Python's chmod (read-only at the file level) AND by the Windows user-profile boundary (faces/ is under the user's home directory anyway).

**Test matrix:**
- POSIX tests (`@pytest.mark.skipif(sys.platform == 'win32')`) — assert os.stat mode is 0600.
- Windows tests (`@pytest.mark.skipif(sys.platform != 'win32')`) — patch subprocess.run to spy on icacls invocation; do NOT actually invoke icacls in CI (CI runners may not have icacls available; user's local dev machine has it).
- Cross-platform tests (no skip) — assert file content + existence + cleanup behavior. The semantics matter on both platforms.

---

## 5. Pre-mortem additions (per strict-mode §1)

Phase 0 listed 10 failure modes. Plan v1 adds 1 more from auditor's P4 review and refines mitigation for §3.5 (CSRF):

### §3.11 — User shares `faces/.dashboard_token` directly (new)

**Failure:** User posts contents of `faces/` to GitHub issue for debugging. `.dashboard_token` is exposed. Attacker who reads the issue has the token.

**Mitigation:** Documented limitation. Same problem any file-based provisioning has (SSH host keys, `/etc/machine-id`, etc.). Future S2.X could move to OS keyring storage (Linux: libsecret; Windows: Credential Manager; macOS: Keychain). Not in S2 scope.

**Tagged for known-limitations.** Forward-tracked as "OS-keyring storage" follow-up.

### §3.5 (CSRF mitigation refined)

The auditor's P5 concern about GET method logging interacts with the CSRF analysis. Even though `SameSite=Strict` blocks cross-origin cookie sends, an attacker who SEES the token (via a leaked URL) can construct a same-origin XSS payload (if XSS exists) OR direct-fetch with the token. **Mitigation chain:**

1. SameSite=Strict blocks cross-origin cookie use.
2. HttpOnly blocks JS read of the cookie.
3. P4 deletes `.dashboard_auth_url` after first auth — the token URL becomes a stale artifact, not a recovery affordance.
4. The token file `.dashboard_token` is mode 0600 / ACL-restricted — only local user can read.

Defense-in-depth holds even under partial breach assumptions.

---

## 6. Multi-direction invariant trace (refined per Plan v1 surface changes)

### Forward

- **P0.S8 (rate limiting)** — keys on cookie value. Confirmed unchanged.
- **S2 tripwire refactor (P0.0.1)** — `test_dashboard_package_json_scripts_explicitly_bind_localhost` BODY changes; the invariant ("default bind localhost; LAN opt-out requires explicit env") moves to a new surface. The existing test_dashboard_next_config_has_no_lan_hostname + test_dashboard_env_local_has_no_lan_override stay unchanged (they guard layers S2 doesn't move).

### Backward

- **No new upstream producer.** Pipeline boot is the only writer to `.dashboard_token`. Dashboard's `/api/auth` is the only writer to the cookie (Set-Cookie header). The auth-URL artifact has 2 writers (pipeline at boot generates, /api/auth deletes after consumption) — these are sequential, not concurrent.

### Sideways

- **Concurrent writers to `.dashboard_token`:** none. Pipeline writes once at first boot. Bookkeeping: if user manually rotates by `rm faces/.dashboard_token`, next pipeline boot regenerates. No file-locking needed.
- **Concurrent writers to `.dashboard_auth_url`:** pipeline boot (write-if-missing) + /api/auth (delete-on-success). Race: pipeline writes URL during /api/auth processing → /api/auth deletes URL → pipeline tries to write again. Avoided by P4 design: pipeline only writes `.dashboard_auth_url` if `.dashboard_token` doesn't exist (i.e., first boot ever). If both files exist on a subsequent boot, pipeline does nothing.

### Lifecycle

Refined per P4:

- **T=0 (first boot):** Pipeline generates token at `.dashboard_token` AND writes URL at `.dashboard_auth_url`. Both mode 0600 / ACL-restricted.
- **T=1 (first auth):** User clicks URL. `/api/auth` validates token, sets cookie, **deletes `.dashboard_auth_url`**, redirects to `/`.
- **T=N (steady state):** Only `.dashboard_token` remains on disk. Cookie carries auth.
- **T=Reset (factory reset):** Both files preserved per D6. (`.dashboard_auth_url` may or may not exist depending on whether first auth has happened; either way, factory-reset doesn't touch it.)
- **T=Manual rotation (deferred):** User manually deletes `.dashboard_token` → next boot regenerates + writes new `.dashboard_auth_url` → first-auth flow repeats. Existing cookies become stale (next request 401s) → user re-clicks new URL.
- **T=∞ (death):** No automatic death. File persists across reboots, OS updates, etc.

---

## 7. 11-gate quality checklist (re-affirmed for Plan v1)

| Gate | Status |
|---|---|
| Correctness — 4-axis invariants traced | ✓ §6 (refined) |
| Security — attack surface mapped | ✓ §5 + Phase 0 §3 (11 failure modes total) |
| Privacy — tier classification | ✓ `.dashboard_token` + cookie value are system_only-tier secrets. NEVER logged. Stdout banner shows the URL file PATH, not the URL content. |
| Performance — hot-path cost | ✓ 1 fs.readFileSync per request, ~0.1ms hot-cache; 0.5 req/s steady state. |
| Observability — logs per D-decision | ✓ D1: token-created log line. D2: 401-on-invalid log line (server-side, no token value). D5: stderr WARNING block. D7: icacls failure WARNING + self-heal log. |
| Test pyramid | ✓ §2 — 28 tests across AST/structural/behavioral. |
| Regression guards | ✓ D3.test 13 (unauth → factory-reset = 401) is THE motivating-failure guard. |
| Pre-mortem | ✓ 11 failure modes (10 from Phase 0 + 1 new §3.11). |
| Multi-direction trace | ✓ §6. |
| Backward compat | ✓ Single breaking change documented: existing dashboard users hit 401 once, click new auth URL. Tripwire refactor banked at §1.P5. |
| Doc updates | ✓ CLAUDE.md Session entry + complete-plan.md P0.S2 status flip + `to_be_checked.md` entry verbatim from §6 of Phase 0 audit. |

All 11 gates APPLY. No N/A.

---

## 8. Deferred-canary `to_be_checked.md` entry (locked, ready for closure)

Same shape as Phase 0 §6 forecast; minor refinements from P2 + P4 additions:

```markdown
## P0.S2 — Dashboard authentication (closed YYYY-MM-DD)

Surfaces shipped:
- core/dashboard_token.py (NEW): _ensure_token_exists, _verify_token_mode,
  _apply_windows_acl, _restrict_to_owner, _write_auth_url, _atomic_write_secret
- pipeline.py: _ensure_dashboard_token() call early in run() (before _validate_env)
- core/db.py::wipe_all(): comment naming preservation invariant for
  .dashboard_token + .dashboard_auth_url
- dog-ai-dashboard/middleware.ts (NEW): cookie-gated matcher /api/:path*
  + inline allowlist for /api/auth
- dog-ai-dashboard/app/api/auth/route.ts (NEW): GET /api/auth?token=X
  → timingSafeEqual → Set-Cookie + delete .dashboard_auth_url + redirect to /
- dog-ai-dashboard/app/api/factory-reset/route.ts: comment naming preservation
- dog-ai-dashboard/scripts/launch.js (NEW): DASHBOARD_BIND env wrapper
  + double-opt-in for 0.0.0.0 + stderr WARNING block
- dog-ai-dashboard/package.json: scripts changed to `node scripts/launch.js dev|start`
- tests/test_dashboard_bind_tripwire.py: refactored to detect launch.js wrapper
  + assert default-bind localhost in launch.js source

PASS signals (canary log should show):
- [Dashboard] Token created at faces/.dashboard_token (first boot only)
- [Dashboard] First-launch auth URL written to faces/.dashboard_auth_url
- Browser: clicking the auth URL redirects to / + dashboard loads
- All 10 existing /api/* routes return 200 once cookie is set
- After factory reset: dashboard STILL accessible (token preserved); URL file
  state preserved if pre-auth, deleted if post-auth (same as before reset)
- DASHBOARD_BIND unset: launch.js binds 127.0.0.1
- DASHBOARD_BIND=192.168.1.5: stderr "DASHBOARD WARNING" block + bind succeeds
- POSIX: .dashboard_token mode is 0600 after creation AND after self-heal cycle
- Windows: icacls invocation visible in pipeline boot (one line) + token file
  shows ACERJN\<user>:(F) only

FAIL signals (regressions; investigate):
- Anonymous /api/factory-reset succeeds (middleware bypassed)
- /api/status returns data without dogai_session cookie
- /api/people/<id> or /api/gallery-audit/<id> returns 200 without cookie
  (dynamic-route invariant guard fired)
- Token URL appears verbatim in terminal_output*.md archives
- .dashboard_auth_url survives a successful auth (P4 delete missed)
- .dashboard_auth_url deleted on FAILED auth (would burn legitimate URL on
  user's typo)
- DASHBOARD_BIND=0.0.0.0 without ALLOW_ANY succeeds (double-opt-in bypass)
- icacls failure crashes pipeline boot (should WARN + continue)

Test scenario:
1. Fresh install, no .dashboard_token, no .dashboard_auth_url
2. Start pipeline → verify both files created mode 0600 (POSIX) /
   user-only ACL (Windows)
3. Verify stdout banner mentions the file PATH (not the URL)
4. Open dashboard at 127.0.0.1:3000 → expect 401 (no cookie)
5. cat faces/.dashboard_auth_url → get the URL → click it
6. Expect redirect to / + dashboard loads + .dashboard_auth_url is now gone
7. Refresh dashboard several times → status loads (cookie persistent)
8. Trigger factory reset → wait for completion → refresh → dashboard
   STILL works (token survived)
9. Stop pipeline, manually `rm faces/.dashboard_token`, restart →
   new token + new .dashboard_auth_url generated; old cookie 401s
10. Set DASHBOARD_BIND=192.168.0.50 → start dashboard → stderr WARNING
    block visible; LAN access works
11. Set DASHBOARD_BIND=0.0.0.0 → expect hard error
12. Set DASHBOARD_BIND=0.0.0.0 + DASHBOARD_BIND_ALLOW_ANY=1 → expect
    WARNING + bind succeeds
13. (Windows) icacls faces\.dashboard_token → verify only current user
    has Full Control

Dependencies on other specs:
- Composes with P0.S8 (rate limiting) when that ships — cookie value
  becomes rate-limit key
- Refactors P0.0.1 S2 tripwire (assertion moves from package.json to
  scripts/launch.js)

Known limitations (banked accepted-with-rationale):
- Single-user / single-token (S2.X: per-device rotation, OS keyring storage)
- TLS not enforced; cookie Secure=false (S2.X: flip on TLS migration)
- GET method on /api/auth — token in URL is acceptable for localhost-only
  HTTP; FORWARD-TRACKED S2.X follow-up: flip to POST-with-form-body when
  TLS/reverse-proxy logs request lines anywhere
- User sharing faces/.dashboard_token directly leaks the token —
  fundamental file-provisioning limit; S2.X: OS keyring storage
- Windows icacls is best-effort — if icacls fails, WARNING logged,
  pipeline continues; Python os.chmod still sets read-only flag
- Token rotation is manual (rm + restart); S2.X: rotation tool
- .dashboard_auth_url leaked before first auth (user shares faces/
  pre-click) — acceptable for solo-canary discipline; user can rm the
  URL file and reissue via rm .dashboard_token + restart
```

This entry will land in `c:\Users\jagan\dog-ai\to_be_checked.md` verbatim at closure (auditor will cross-check).

---

## 9. Plan v2 forecast

Plan v2 (post-auditor v1 review) likely refinements:
- Module placement: confirm `core/dashboard_token.py` vs inline in `pipeline.py` (Phase 0 forecast leaned new module; Plan v1 locks new module for testability)
- Exact `secrets.token_urlsafe()` byte count: locked to 32 bytes (43 chars urlsafe)
- Cookie `Max-Age` exact value (10y = 315360000s)
- Edge cases auditor may surface: token file gets corrupted, partial cookie sent, browser cookie eviction, multi-tab login race

Anticipated auditor v1 precision items: 1-3. Plan v2 will land all + close.

---

## 10. Auditor-Q5 calibration (banking continuation)

Auditor's pre-spec estimate: 16-22 tests. Plan v1 locks 28. **OVER by 6 (~27% over upper bound).**

Per `feedback_auditor_q5_estimates_trail_grep.md` pattern history:
- D-B HIGH 40% (21→15) — over-estimated; actual smaller
- D-D LOW 4× (40→130) — under-estimated; actual larger
- D-E LOW 60% — under
- P0.S7.5 ON-TARGET (12-19→16-17)
- P0.S7.5.1 ON-TARGET → slight HIGH-BY-20%
- P0.S7.5.2 ON-TARGET → slight HIGH-BY-7%

P0.S2 lands at **slight HIGH-BY-27% from upper bound** (28 vs 22). The over-estimate is driven by:
- D7's 2 separate Windows ACL tests (P3 lock)
- D6's auth-url preservation companion test (P4)
- D2's auth-url delete behavioral test (P4)
- D3's dynamic-route coverage test (P2)
- A handful of structural-invariant tests Phase 0 forecast didn't enumerate

This is the **4th ON-TARGET-with-slight-overage instance in a row** (P0.S7.5, P0.S7.5.1, P0.S7.5.2, P0.S2). Phase 0 granularity sub-observation — 7 D-decisions with concrete named edit sites + behavioral + AST split — produces estimates that land ON-TARGET with slight overage in the precision-item phase.

**Banking:** auditor-Q5 6th instance at architect-memory. Pattern is solidifying.

---

## 11. Strict-mode operational test (Plan v1)

- [x] Pre-mortem section refined (§5 — 11 failure modes)
- [x] Multi-direction trace refined for new surfaces (§6)
- [x] Quality-gate checklist re-affirmed (§7)
- [x] Cross-spec impact analysis re-verified (§1.P5, §6)
- [x] Closure-audit scheduled (implicit — will execute per discipline)

All 5 strict-mode tests pass. 6th consecutive application holds (P0.S7.5.1 v1+v2+closure, P0.S7.5.2 Phase 0+v1+v2+closure, P0.S2 Phase 0+v1).

---

**End of Plan v1.**

Ready to share with auditor for Plan v2 sign-off cycle.
