"""tests/test_dashboard_auth_helper.py — dashboard auth gate (Node-runtime helper).

Replaces tests/test_dashboard_middleware.py (deleted). The P0.S2/S8 auth gate
moved OUT of the Edge-runtime middleware (which could not run fs/Buffer/crypto
in Next.js 14) and INTO a Node-runtime helper `lib/requireAuth.ts` called at the
top of every gated /api/* route handler.

Spec: tests/dashboard_auth_edge_runtime_fix_spec.md (2026-05-30) — canary #1.

Coverage:
  - Migration invariant: middleware.ts has no fs/Buffer/crypto (deleted, or
    Edge-safe cookie-presence only).
  - lib/requireAuth.ts preserves every P0.S2/S8 invariant: fresh-read-per-request,
    constant-time compare + length pre-check, the two distinguishable 401s,
    rate-limit-AFTER-auth ordering, 429 + Retry-After, LRUCache config.
  - Forward-property: every app/api/**/route.ts EXCEPT auth calls requireAuth(
    (this structural guarantee replaces the old central matcher — a future route
    that forgets the guard fails CI).

NOTE (the entire lesson — §7 of the spec): source-inspection proves SHAPE, not
RUNTIME. These tests are the structural complement to the §4 live-verification
(no-cookie → 401 Unauthorized; cookied → 200), which is the actual proof the
gate works in the Edge/Node runtime split. `Full-suite-run-is-the-universal-
completeness-proof` applied at the dashboard layer.
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

_DASHBOARD = Path(__file__).resolve().parent.parent / "karaos-dashboard"
_HELPER_TS = _DASHBOARD / "lib" / "requireAuth.ts"
_MIDDLEWARE_TS = _DASHBOARD / "middleware.ts"
_API_DIR = _DASHBOARD / "app" / "api"


@pytest.fixture(scope="module")
def helper_src() -> str:
    assert _HELPER_TS.exists(), (
        f"lib/requireAuth.ts must exist at {_HELPER_TS} — it is the Node-runtime "
        "auth gate that replaced the Edge-incompatible middleware (canary #1 fix)."
    )
    return _HELPER_TS.read_text(encoding="utf-8")


# ───────────────────────────────────────────────────────────────────────
# Migration invariant — the bug (Node APIs in Edge middleware) is gone
# ───────────────────────────────────────────────────────────────────────


def test_middleware_has_no_node_only_apis():
    """The Edge-incompatible auth is gone: middleware.ts is deleted OR (if a
    belt-and-braces cookie-presence stub remains) contains NO fs/Buffer/crypto.

    This is the regression guard for canary #1: Next.js 14 runs middleware in
    the Edge runtime, where fs.readFileSync / Buffer / crypto.timingSafeEqual
    do not exist — using them made the token read throw and 401'd every route.
    """
    if not _MIDDLEWARE_TS.exists():
        return  # deleted — the recommended disposition; nothing to check
    src = _MIDDLEWARE_TS.read_text(encoding="utf-8")
    for node_api in ("fs.readFileSync", "crypto.timingSafeEqual", "Buffer.from"):
        assert node_api not in src, (
            f"middleware.ts still contains the Edge-incompatible {node_api!r} — "
            "this is exactly canary #1. The token read + compare must live in the "
            "Node-runtime lib/requireAuth.ts, NOT in Edge middleware."
        )


# ───────────────────────────────────────────────────────────────────────
# Helper preserves the P0.S2 auth invariants
# ───────────────────────────────────────────────────────────────────────


def test_helper_exports_require_auth(helper_src):
    """requireAuth(req) is exported and returns NextResponse | null (deny | pass)."""
    assert re.search(r"export function requireAuth\(\s*req:\s*NextRequest\s*\)", helper_src), (
        "lib/requireAuth.ts must export `function requireAuth(req: NextRequest)`"
    )
    assert "NextResponse | null" in helper_src, (
        "requireAuth must return `NextResponse | null` (NextResponse=deny, null=pass)"
    )


def test_helper_reads_token_fresh_per_request(helper_src):
    """P0.S2 D4 — fresh token read inside requireAuth (no module-scope cache).

    _tokenPath() resolves at call time and fs.readFileSync is inside the
    requireAuth body, so manual token rotation / corruption recovery is picked
    up without a restart.
    """
    assert "function _tokenPath()" in helper_src, "must resolve token path at call time"
    assert "process.cwd(), '..', 'faces', '.dashboard_token'" in helper_src, (
        "token path must be project-root faces/.dashboard_token relative to dashboard CWD"
    )
    body_start = helper_src.find("export function requireAuth")
    assert body_start > 0
    body = helper_src[body_start:]
    assert "fs.readFileSync" in body, (
        "fs.readFileSync MUST be inside requireAuth body (fresh-read-per-request)"
    )
    module_scope = helper_src[:body_start]
    assert "fs.readFileSync" not in module_scope, (
        "module-scope fs.readFileSync caches the token at boot — forbidden (P0.S2 D4)"
    )


def test_helper_constant_time_compare_with_length_precheck(helper_src):
    """P0.S2 D2 test 8 — length pre-check THEN timingSafeEqual."""
    assert "if (a.length !== b.length) return false" in helper_src, (
        "length pre-check must short-circuit before timingSafeEqual"
    )
    assert "crypto.timingSafeEqual(Buffer.from(a, 'utf8'), Buffer.from(b, 'utf8'))" in helper_src, (
        "constant-time compare must use crypto.timingSafeEqual on same-length buffers"
    )


def test_helper_two_distinguishable_401s(helper_src):
    """P0.S2 D2 — distinct 401 bodies: missing-token vs bad/absent cookie."""
    assert "Pipeline not started — token not yet generated" in helper_src, (
        "missing-token 401 body must be the distinguishable 'Pipeline not started' message"
    )
    assert "'Unauthorized'" in helper_src or '"Unauthorized"' in helper_src, (
        "bad/absent-cookie 401 body must be 'Unauthorized'"
    )
    assert "{ status: 401 }" in helper_src or "{status: 401}" in helper_src


def test_helper_token_read_is_enoent_tolerant(helper_src):
    """Missing token file → 401 (not 500): try/catch around fs.readFileSync."""
    assert "try {" in helper_src and "catch" in helper_src, (
        "fs.readFileSync must be wrapped in try/catch (ENOENT/EACCES → 401, not 500)"
    )


def test_helper_reads_karaos_session_cookie(helper_src):
    assert "cookies.get('karaos_session')" in helper_src or \
           'cookies.get("karaos_session")' in helper_src, (
        "requireAuth must read the locked karaos_session cookie"
    )


# ───────────────────────────────────────────────────────────────────────
# P0.S8 rate-limit invariants — moved from middleware to the helper
# ───────────────────────────────────────────────────────────────────────


def test_p0_s8_d1_lru_cache_dependency_present():
    """P0.S8 D1: lru-cache is still a dashboard dependency (unchanged by the fix)."""
    pkg = json.loads((_DASHBOARD / "package.json").read_text(encoding="utf-8"))
    deps = pkg.get("dependencies", {})
    assert "lru-cache" in deps, "lru-cache must remain in package.json dependencies"
    version = deps["lru-cache"]
    assert version.startswith("^10") or version.startswith("10"), (
        f"lru-cache should be ^10.x per Q1 LOCK; got {version!r}"
    )


def test_p0_s8_d2_lru_cache_instance_config(helper_src):
    """P0.S8 D2: LRUCache<string, number[]> with max=100, ttl=60_000 in the helper."""
    assert "import { LRUCache } from 'lru-cache'" in helper_src
    assert "new LRUCache<string, number[]>" in helper_src
    assert "max: 100," in helper_src, (
        "LRUCache max must be 100 (trailing comma — `max: 100` is a prefix of `max: 1000`)"
    )
    assert "ttl: 60_000" in helper_src or "ttl: 60000" in helper_src


def test_p0_s8_d3_rate_limit_after_auth_ordering(helper_src):
    """P0.S8 D3 ORDERING INVARIANT — rate-limit AFTER _safeEqual (load-bearing).

    Failed-auth requests (returned before the rate-limit block) must NOT
    populate the cache / consume the per-token budget.
    """
    safeequal_idx = helper_src.find("_safeEqual(cookieValue, fileToken)")
    rate_limit_idx = helper_src.find("_rateLimitCache.get(cookieValue)")
    pass_through_idx = helper_src.find("// Authenticated + within rate limit")
    assert safeequal_idx > 0, "_safeEqual(cookieValue, fileToken) must be present"
    assert rate_limit_idx > 0, "_rateLimitCache.get(cookieValue) must be present"
    assert pass_through_idx > 0, "pass-through comment must be present"
    assert safeequal_idx < rate_limit_idx < pass_through_idx, (
        f"ORDERING INVARIANT violation: rate-limit (idx={rate_limit_idx}) must sit "
        f"AFTER _safeEqual (idx={safeequal_idx}) and BEFORE pass-through "
        f"(idx={pass_through_idx})."
    )
    assert "ORDERING INVARIANT" in helper_src, (
        "the rate-limit-AFTER-auth rule must be documented in the helper"
    )


def test_p0_s8_d3_sliding_window_logic(helper_src):
    assert "now - ts < windowMs" in helper_src
    assert "windowMs = 60_000" in helper_src or "windowMs = 60000" in helper_src
    assert "limit = 60" in helper_src
    assert "recent.length >= limit" in helper_src


def test_p0_s8_d3_429_response_shape(helper_src):
    assert "status: 429" in helper_src
    assert "'Retry-After'" in helper_src or '"Retry-After"' in helper_src
    assert "retry_after_seconds" in helper_src
    assert "'Rate limit exceeded'" in helper_src or '"Rate limit exceeded"' in helper_src


# ───────────────────────────────────────────────────────────────────────
# Forward-property — the structural guarantee that replaces the matcher
# ───────────────────────────────────────────────────────────────────────


def _route_files() -> list[Path]:
    return sorted(p for p in _API_DIR.rglob("route.ts") if ".next" not in p.parts)


def test_every_gated_route_calls_require_auth():
    """FORWARD-PROPERTY (the key test): every app/api/**/route.ts EXCEPT auth
    contains a requireAuth( call. This replaces the deleted central middleware
    matcher — a future route that ships without the guard fails CI here.

    Each route's requireAuth( call count must be >= its exported handler count
    (so a multi-handler file like gallery-audit/[id] guards BOTH GET and DELETE).
    """
    routes = _route_files()
    assert routes, "sanity: app/api/**/route.ts must glob non-empty"

    violations: list[str] = []
    saw_auth = False
    for rf in routes:
        rel = rf.relative_to(_API_DIR).as_posix()
        src = rf.read_text(encoding="utf-8")
        n_handlers = len(re.findall(
            r"export\s+(?:async\s+)?function\s+(?:GET|POST|PUT|PATCH|DELETE)\b", src
        ))
        n_guards = src.count("requireAuth(")
        if rel.startswith("auth/"):
            saw_auth = True
            # /api/auth mints the cookie — it MUST NOT be gated.
            if n_guards != 0:
                violations.append(f"{rel}: /api/auth must NOT call requireAuth (it mints the cookie)")
            continue
        if n_guards < n_handlers or n_guards == 0:
            violations.append(
                f"{rel}: {n_handlers} handler(s) but only {n_guards} requireAuth( call(s) — "
                "every gated handler must call requireAuth(req) at the top"
            )
    assert saw_auth, "sanity: /api/auth/route.ts must exist"
    assert not violations, (
        "Forward-property FAILED — these routes are not (fully) guarded:\n  "
        + "\n  ".join(violations)
        + "\n\nFix: add `const denied = requireAuth(req); if (denied) return denied` "
        "at the top of each handler (and widen GET() → GET(req: NextRequest))."
    )


def test_auth_route_is_not_gated():
    """/api/auth stays un-gated (entry point that mints the session cookie)."""
    auth = _API_DIR / "auth" / "route.ts"
    assert auth.exists(), "/api/auth/route.ts must exist"
    assert "requireAuth(" not in auth.read_text(encoding="utf-8"), (
        "/api/auth must NOT be gated — gating the cookie-minting route is chicken/egg"
    )
