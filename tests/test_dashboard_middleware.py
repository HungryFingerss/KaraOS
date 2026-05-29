"""tests/test_dashboard_middleware.py — P0.S2 D3 middleware coverage + D4 file-read.

Plan v2 §12 Phase 2 explicitly authorized either (a) Next.js subprocess
fixture for behavioral tests OR (b) AST/structural source-inspection for
checkable invariants. This file uses (b) for every test — both the
middleware logic flow AND the API-coverage invariant are structurally
verifiable from source without a live server. End-of-P0.R11 canary week
validates the behavioral surface end-to-end.

Tests covered (per Plan v1 §2):
  - D3 test 10: every /api/* route gated by middleware (allowlist = {/api/auth})
  - D3 test 11: unauthenticated request → 401 (logic flow)
  - D3 test 12: authenticated request → NextResponse.next() (logic flow)
  - D3 test 13: factory-reset gated (route exists in glob; middleware matcher covers it)
  - D3 test 14: dynamic [id] routes gated (matcher = '/api/:path*' covers them)
  - D4 test 15: no module-scope token cache — fs.readFileSync inside middleware body
  - D4 test 16: missing token file → 401 (logic flow)
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

from pathlib import Path

import pytest


_DASHBOARD = Path(__file__).resolve().parent.parent / "dog-ai-dashboard"
_MIDDLEWARE_TS = _DASHBOARD / "middleware.ts"


@pytest.fixture(scope="module")
def middleware_src() -> str:
    """Read middleware.ts source once per module."""
    assert _MIDDLEWARE_TS.exists(), (
        f"middleware.ts must exist at {_MIDDLEWARE_TS}; P0.S2 spec requires it"
    )
    return _MIDDLEWARE_TS.read_text(encoding="utf-8")


# ───────────────────────────────────────────────────────────────────────
# D3 — middleware coverage (5 tests)
# ───────────────────────────────────────────────────────────────────────


def test_every_api_route_is_gated_by_middleware(middleware_src):
    """D3 test 10 — structural: glob `app/api/**/route.ts`, build set of
    route paths; assert middleware matcher covers all, and the inline
    allowlist contains exactly `/api/auth`.

    The matcher `/api/:path*` covers every `/api/*` route by Next.js
    convention. The allowlist (inline `if (req.nextUrl.pathname ===
    '/api/auth') return NextResponse.next()`) is the carve-out that
    must exist + must contain ONLY `/api/auth`.
    """
    # Collect all /api/* route paths from filesystem (excluding .next build)
    routes = []
    for route_file in (_DASHBOARD / "app" / "api").rglob("route.ts"):
        if ".next" in route_file.parts:
            continue
        # Compute the URL path from the file location
        rel = route_file.relative_to(_DASHBOARD / "app").parent
        api_path = "/" + str(rel).replace("\\", "/")
        routes.append(api_path)

    assert "/api/status" in routes, "sanity: existing /api/status must be present"
    assert "/api/factory-reset" in routes, "sanity: factory-reset must be present"
    assert "/api/auth" in routes, "P0.S2 Phase 2 must create /api/auth route"

    # The matcher must be exactly '/api/:path*' (Next.js convention for all
    # /api/* routes). Any other pattern leaves routes ungated.
    assert "'/api/:path*'" in middleware_src or '"/api/:path*"' in middleware_src, (
        "middleware.ts matcher MUST be '/api/:path*' so every /api/* route "
        "is gated by default. Future routes are protected without opt-in."
    )

    # Inline allowlist must contain '/api/auth' and ONLY '/api/auth'.
    # Pattern: `req.nextUrl.pathname === '/api/auth'` then NextResponse.next()
    assert "'/api/auth'" in middleware_src or '"/api/auth"' in middleware_src, (
        "middleware.ts MUST inline-allowlist '/api/auth' (the one route "
        "that mints the session cookie — gating it would create chicken/egg)"
    )

    # Scan for any OTHER allowlisted paths — if found, surface them. The
    # allowlist must be exactly the single '/api/auth' entry.
    import re as _re
    allowed = _re.findall(r"pathname\s*===\s*['\"](/api/[^'\"]+)['\"]", middleware_src)
    assert set(allowed) == {"/api/auth"}, (
        f"middleware allowlist MUST contain exactly /api/auth; found: {allowed}. "
        f"Extra allowlisted routes are auth bypass vectors."
    )


def test_unauthenticated_request_returns_401_logic_path(middleware_src):
    """D3 test 11 (logic-flow) — middleware returns 401 when cookie absent.

    Structural pattern: cookies.get('dogai_session')?.value falsy →
    NextResponse.json({error: 'Unauthorized'}, {status: 401}).
    """
    # Cookie read pattern
    assert "cookies.get('dogai_session')" in middleware_src or \
           'cookies.get("dogai_session")' in middleware_src, (
        "middleware MUST read the dogai_session cookie via cookies.get()"
    )
    # 401 on absent cookie — must appear in source
    assert "{ status: 401 }" in middleware_src or "{status: 401}" in middleware_src, (
        "middleware MUST return status 401 on unauth (absent cookie OR mismatch)"
    )
    # The "Unauthorized" body string is the locked auth-fail shape
    assert "Unauthorized" in middleware_src, (
        "middleware MUST emit 'Unauthorized' for mismatch/absent-cookie failures"
    )


def test_authenticated_request_passes_through(middleware_src):
    """D3 test 12 (logic-flow) — on cookie match, middleware returns
    NextResponse.next() (pass-through to the underlying route handler).
    """
    assert "NextResponse.next()" in middleware_src, (
        "middleware MUST call NextResponse.next() on successful auth — "
        "absence means even authenticated requests get blocked"
    )


def test_factory_reset_is_gated_by_middleware():
    """D3 test 13 — `/api/factory-reset` exists as a route AND is covered
    by the `/api/:path*` matcher (verified by test 10) AND is NOT in the
    allowlist (verified by test 10's set equality).

    This test exists separately to make the regression-guard against
    "anonymous attacker can factory-reset" explicit — the motivating
    failure of the entire P0.S2 spec.
    """
    factory_reset = _DASHBOARD / "app" / "api" / "factory-reset" / "route.ts"
    assert factory_reset.exists(), (
        "factory-reset route MUST exist — sanity check"
    )
    # Middleware-gating is enforced via matcher (covered by test 10's pattern check
    # + the absence of '/api/factory-reset' from the allowlist).


def test_middleware_gates_dynamic_id_routes(middleware_src):
    """D3 test 14 (Plan v1 P2) — dynamic-segment routes like
    `/api/people/[id]/route.ts` are gated by the `/api/:path*` matcher.

    Pattern: Next.js `:path*` matcher covers all subpaths including
    dynamic-segment routes. Both `/api/people/jagan_001` and
    `/api/gallery-audit/some_id` must route through the middleware.
    """
    # Sanity: dynamic-segment routes exist
    dynamic_routes = [
        _DASHBOARD / "app" / "api" / "people" / "[id]" / "route.ts",
        _DASHBOARD / "app" / "api" / "gallery-audit" / "[id]" / "route.ts",
    ]
    for r in dynamic_routes:
        assert r.exists(), f"dynamic route MUST exist for D3 test 14: {r}"

    # Matcher pattern `/api/:path*` covers dynamic segments by Next.js convention.
    # No special allowlist branch for dynamic IDs — verified by test 10's set check
    # which asserts allowlist == {/api/auth}.
    assert "/api/:path*" in middleware_src, (
        "matcher '/api/:path*' MUST cover dynamic-segment routes; without it, "
        "/api/people/<id> and /api/gallery-audit/<id> would be ungated"
    )


# ───────────────────────────────────────────────────────────────────────
# D4 — file-read invariant (2 tests)
# ───────────────────────────────────────────────────────────────────────


def test_middleware_reads_token_file_on_every_request(middleware_src):
    """D4 test 15 — middleware.ts MUST NOT cache the token at module
    scope. The `fs.readFileSync` call MUST be inside the `middleware`
    function body so each request re-reads the on-disk file. This is
    the structural-invariant complement to the Python-side
    `test_ensure_dashboard_token_reads_file_on_every_call`.
    """
    # The file must contain a function called `middleware` (the Next.js entry point)
    assert "export function middleware" in middleware_src, (
        "middleware.ts MUST export a function named 'middleware'"
    )
    # fs.readFileSync MUST appear inside the middleware body (not at module scope)
    # Find the middleware function body
    import re as _re
    # Locate the start of `export function middleware(...)`
    m_start = middleware_src.find("export function middleware")
    assert m_start > 0
    fn_body = middleware_src[m_start:]
    assert "fs.readFileSync" in fn_body, (
        "middleware function body MUST contain fs.readFileSync — token must be "
        "re-read on EVERY request. Module-scope const TOKEN = fs.readFileSync(...) "
        "would silently cache the token and break manual rotation / corruption recovery."
    )
    # Belt-and-braces: module-scope (BEFORE the middleware function) MUST NOT
    # contain a `const TOKEN = fs.readFileSync(...)` pattern.
    module_scope = middleware_src[:m_start]
    # Reject module-scope `fs.readFileSync` (excludes function references, imports).
    # The legitimate module-scope imports use `import fs from 'fs'`, not the readFileSync call.
    assert "fs.readFileSync" not in module_scope, (
        "module-scope fs.readFileSync detected in middleware.ts — this caches "
        "the token at server boot. MUST be inside middleware function body."
    )


def test_middleware_returns_401_when_token_file_missing(middleware_src):
    """D4 test 16 (logic-flow) — `try/catch` around `fs.readFileSync`
    returns 401 (not 500) when the token file is missing. The 401
    body distinguishes "pipeline not started" from generic Unauthorized
    so the operator can diagnose.
    """
    # Pattern: try { fs.readFileSync(...) } catch { return NextResponse.json(...401)}
    assert "Pipeline not started" in middleware_src, (
        "middleware MUST emit a distinguishable 401 on ENOENT — body should "
        "include 'Pipeline not started' so operator can tell apart 'no token' "
        "from 'wrong cookie'"
    )
    # try/catch over readFileSync
    assert "try {" in middleware_src and "catch" in middleware_src, (
        "fs.readFileSync MUST be wrapped in try/catch (ENOENT-tolerant); "
        "without this, the route 500s on missing token instead of 401-ing"
    )


# ───────────────────────────────────────────────────────────────────────
# P0.S8 D4 — rate-limiting source-inspection coverage (5 tests)
# ───────────────────────────────────────────────────────────────────────


def test_p0_s8_d1_lru_cache_dependency_added():
    """P0.S8 D1: dog-ai-dashboard/package.json must declare lru-cache dependency."""
    import json
    pkg = json.loads((_DASHBOARD / "package.json").read_text(encoding="utf-8"))
    deps = pkg.get("dependencies", {})
    assert "lru-cache" in deps, (
        "P0.S8 D1: lru-cache must be in dog-ai-dashboard/package.json dependencies"
    )
    # Version pin: ^10.x or compatible. Reject obviously-wrong versions.
    version = deps["lru-cache"]
    assert version.startswith("^10") or version.startswith("10"), (
        f"P0.S8 D1: lru-cache version should be ^10.x per Q1 LOCK; got {version!r}"
    )


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
    # Config: max=100, ttl=60_000. Use trailing comma in substring to avoid
    # prefix-collision with `max: 1000`, `max: 10000`, etc. (regression gap
    # surfaced by P0.S8 Phase 4 §2.5 deliberate-regression check (b) under
    # the ### Induction-surfaces-invariant-gaps discipline — original
    # assertion `"max: 100" in src` matched `max: 1000` as a prefix.)
    assert "max: 100," in middleware_src, (
        "P0.S8 D2 Q2 LOCK: LRUCache max must be 100 (with trailing comma; "
        "loose `max: 100` substring is a prefix of `max: 1000`)"
    )
    assert "ttl: 60_000," in middleware_src or "ttl: 60000," in middleware_src, (
        "P0.S8 D2: LRUCache ttl must be 60_000 (or 60000) ms (with trailing comma; "
        "loose `ttl: 60_000` substring is a prefix of `ttl: 60_0000`)"
    )


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
