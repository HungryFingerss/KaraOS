"""tests/test_dashboard_auth_route.py — P0.S2 D2 auth route + D6 preservation.

Plan v2 §12 Phase 2 + §3.12 multi-tab idempotency. Source-inspection
strategy per Plan v2 §12 note ("AST source-inspection alone for some
tests"). Live-server behavioral validation deferred to end-of-P0.R11
canary week per `feedback_deferred_canary_strategy.md`.

Tests covered (per Plan v1 §2 D2):
  - D2 test 5: valid token sets cookie + 302 redirect (structural)
  - D2 test 6: invalid token → 401, no cookie (structural)
  - D2 test 7: missing ?token → 400 (structural)
  - D2 test 8: constant-time compare (AST/structural)
  - D2 test 9: success deletes .dashboard_auth_url (structural)
  - D2 test §3.12 (NEW): double-click idempotency (ENOENT-tolerant unlink)
  - D6 test 24: failure does NOT delete .dashboard_auth_url (structural ordering)
"""

# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025-2026 The KaraOS Authors

from __future__ import annotations

import re
from pathlib import Path

import pytest


_DASHBOARD = Path(__file__).resolve().parent.parent / "dog-ai-dashboard"
_AUTH_ROUTE_TS = _DASHBOARD / "app" / "api" / "auth" / "route.ts"
_FACTORY_RESET_TS = _DASHBOARD / "app" / "api" / "factory-reset" / "route.ts"


@pytest.fixture(scope="module")
def auth_src() -> str:
    """Read auth/route.ts source once per module."""
    assert _AUTH_ROUTE_TS.exists(), (
        f"app/api/auth/route.ts must exist at {_AUTH_ROUTE_TS}; "
        "P0.S2 spec requires it"
    )
    return _AUTH_ROUTE_TS.read_text(encoding="utf-8")


# ───────────────────────────────────────────────────────────────────────
# D2 — auth route (6 tests)
# ───────────────────────────────────────────────────────────────────────


def test_auth_valid_token_sets_cookie_and_redirects(auth_src):
    """D2 test 5 (structural) — on token match, route sets the
    `dogai_session` cookie with locked attributes AND returns 302.

    Locked cookie shape per Plan v1 §1.D2:
      - name: 'dogai_session'
      - httpOnly: true
      - sameSite: 'strict'
      - path: '/'
      - maxAge: 315360000 (10 years)
    """
    # 302 redirect via NextResponse.redirect
    assert "NextResponse.redirect" in auth_src, (
        "auth route MUST use NextResponse.redirect for 302 on success"
    )
    # status 302 explicit
    assert "302" in auth_src, "302 status code MUST be explicit"
    # Cookie name + locked attributes
    assert "'dogai_session'" in auth_src or '"dogai_session"' in auth_src
    assert "httpOnly: true" in auth_src
    # SameSite=Strict (lowercase 'strict' per Next.js cookie API)
    assert ("sameSite: 'strict'" in auth_src or 'sameSite: "strict"' in auth_src), (
        "cookie MUST be SameSite=Strict per Plan v1 §1.D2"
    )
    assert "path: '/'" in auth_src or 'path: "/"' in auth_src
    assert "maxAge: 315360000" in auth_src, (
        "maxAge MUST be 315360000 (10 years) per Plan v1 §1.D2 locked attribute"
    )


def test_auth_invalid_token_returns_401_no_cookie(auth_src):
    """D2 test 6 (structural) — mismatch branch returns 401 JSON +
    NO cookies.set. The branch shape:
      if (!_safeEqual(...)) return NextResponse.json({error: 'Unauthorized'}, {status: 401})
    """
    # Find the mismatch return — must be 401 + NO cookies.set on same path
    assert "Unauthorized" in auth_src
    # 401 status appears in source
    assert "401" in auth_src

    # Structural check: the `_safeEqual` negation branch returns a NextResponse.json,
    # NOT a NextResponse.redirect with Set-Cookie.
    # Pattern: `if (!_safeEqual(...))` → must be followed by NextResponse.json
    m = re.search(r"if\s*\(\s*!_safeEqual\([^)]+\)\s*\)\s*\{?\s*return\s+NextResponse\.json", auth_src)
    assert m is not None, (
        "auth route MUST guard against token mismatch with explicit "
        "`if (!_safeEqual(...)) return NextResponse.json(...401)` — without "
        "this shape, mismatch could fall through to the success path"
    )


def test_auth_missing_token_param_returns_400(auth_src):
    """D2 test 7 (structural) — absent `?token=` returns 400 (distinct
    from 401 mismatch). The branch shape:
      const tokenParam = req.nextUrl.searchParams.get('token')
      if (!tokenParam) return NextResponse.json({error: '...'}, {status: 400})
    """
    assert "searchParams.get('token')" in auth_src or \
           'searchParams.get("token")' in auth_src
    assert "400" in auth_src, (
        "missing-token branch MUST return 400 (not 401 — operator distinction "
        "between 'forgot URL parameter' vs 'wrong token')"
    )
    # The absent-param branch must precede the file-read + compare branches
    param_idx = auth_src.find("searchParams.get")
    file_read_idx = auth_src.find("fs.readFileSync")
    assert param_idx < file_read_idx, (
        "missing-param check MUST precede file read; otherwise we waste an "
        "I/O cycle on a clearly-invalid request"
    )


def test_auth_uses_constant_time_compare(auth_src):
    """D2 test 8 (AST/structural) — token comparison uses
    `crypto.timingSafeEqual` with length pre-check, NOT bare `===`.

    Locked pattern per Plan v1 §2 D2 test 8:
      1. length pre-check (a.length !== b.length → false short-circuit)
      2. crypto.timingSafeEqual(Buffer.from(a), Buffer.from(b))
      3. NO bare `===` for token-on-token compare
    """
    assert "crypto.timingSafeEqual" in auth_src, (
        "auth route MUST use crypto.timingSafeEqual for token compare; "
        "bare === is a timing-attack surface"
    )
    # Length pre-check pattern
    assert ".length !== " in auth_src or ".length != " in auth_src, (
        "constant-time compare MUST include length pre-check — timingSafeEqual "
        "throws on length mismatch, so length-first short-circuits the trivially-wrong case"
    )
    # Ordering: length check precedes timingSafeEqual in the helper body
    helper_start = auth_src.find("_safeEqual")
    assert helper_start > 0
    helper_body = auth_src[helper_start:helper_start + 400]
    length_idx = helper_body.find(".length")
    ts_idx = helper_body.find("timingSafeEqual")
    assert length_idx > 0 and ts_idx > 0 and length_idx < ts_idx, (
        "length check MUST precede timingSafeEqual call — locked ordering "
        "per Plan v1 §2 D2 test 8"
    )

    # Negative: no bare `=== fileToken` or `=== tokenParam` for the token compare
    # (We allow `=== '/api/auth'` etc. in middleware, but in auth route there
    # should be no `=== <tokenVar>` for the validation path.)
    assert "=== fileToken" not in auth_src, (
        "bare === fileToken detected — token compare MUST go through _safeEqual"
    )


def test_auth_success_deletes_auth_url_file(auth_src):
    """D2 test 9 (Plan v1 §1.P4 structural) — on successful validation,
    `.dashboard_auth_url` is deleted AFTER cookie is set (delete is
    hygiene, NOT validation logic).
    """
    # Locate `.dashboard_auth_url` deletion via fs.unlinkSync
    assert "AUTH_URL_PATH" in auth_src or ".dashboard_auth_url" in auth_src, (
        "auth route MUST reference .dashboard_auth_url to delete it on success"
    )
    assert "fs.unlinkSync" in auth_src, (
        "auth route MUST call fs.unlinkSync to delete the auth URL artifact"
    )

    # Plan v2 §3.12: delete is AFTER cookies.set (hygiene), NOT before validation.
    # Structural check: the unlinkSync call MUST appear AFTER the success-path
    # cookies.set call in source order.
    cookies_set_idx = auth_src.find("res.cookies.set")
    unlink_idx = auth_src.find("fs.unlinkSync(AUTH_URL_PATH)")
    if unlink_idx < 0:
        # Fallback: maybe the path is inlined
        unlink_idx = auth_src.find("fs.unlinkSync")
    assert cookies_set_idx > 0
    assert unlink_idx > cookies_set_idx, (
        "Plan v2 §3.12 invariant: .dashboard_auth_url deletion MUST happen "
        "AFTER res.cookies.set; the URL file is a convenience artifact, NOT "
        "validation logic. Deleting BEFORE the cookie would race with the "
        "browser's redirect-follow."
    )


def test_auth_double_click_succeeds_idempotently(auth_src):
    """D2 §3.12 (NEW per Plan v2) — `fs.unlinkSync` for `.dashboard_auth_url`
    MUST be wrapped in try/catch to be ENOENT-tolerant. Second click of
    the auth URL: validation still succeeds (against `.dashboard_token`,
    not the auth URL file), Set-Cookie re-issued (harmless), unlink
    no-ops because file is already gone.

    Plan v2 §3.12 verbatim: "delete-after-success is for the on-disk
    artifact's hygiene, NOT for the validation logic."
    """
    # Pattern: try { fs.unlinkSync(AUTH_URL_PATH) } catch { ... }
    # Find the unlinkSync call and verify it's inside a try block.
    unlink_idx = auth_src.find("fs.unlinkSync")
    assert unlink_idx > 0
    # Walk backwards from unlink_idx looking for a `try {` AFTER the
    # last cookies.set (so we're not matching a try for a different op).
    cookies_set_idx = auth_src.rfind("res.cookies.set", 0, unlink_idx)
    # Between cookies.set and unlinkSync, expect `try {`
    between = auth_src[cookies_set_idx:unlink_idx]
    assert "try {" in between or "try{" in between, (
        "fs.unlinkSync MUST be wrapped in try/catch for double-click "
        "idempotency (Plan v2 §3.12). Without try/catch, the second click "
        "of the auth URL throws ENOENT on the now-missing file."
    )
    # And expect a catch block AFTER the unlink call
    catch_after = auth_src.find("catch", unlink_idx)
    assert catch_after > 0 and catch_after < unlink_idx + 200, (
        "fs.unlinkSync MUST be followed by `catch { ... }` to tolerate "
        "ENOENT on the second click"
    )


# ───────────────────────────────────────────────────────────────────────
# D6 — auth-url preserve on failure (1 test)
# ───────────────────────────────────────────────────────────────────────


def test_auth_failure_does_not_delete_auth_url_file(auth_src):
    """D6 test 24 — wrong-token branch MUST NOT call fs.unlinkSync.
    Wrong attempts don't burn the URL — the user can retry with the
    correct token. Structural ordering check: the unlinkSync call
    appears AFTER the mismatch-401 return statement in source order.
    """
    # Find the mismatch return (NextResponse.json with 401 Unauthorized)
    # and verify fs.unlinkSync appears AFTER it (i.e., in the success
    # path, not the failure path).
    m = re.search(
        r"if\s*\(\s*!_safeEqual\([^)]+\)\s*\)\s*\{?\s*return\s+NextResponse\.json\([^)]*Unauthorized",
        auth_src,
    )
    assert m is not None, (
        "auth route MUST have an early-return on mismatch (Unauthorized 401)"
    )
    mismatch_return_end = m.end()
    unlink_idx = auth_src.find("fs.unlinkSync")
    assert unlink_idx > mismatch_return_end, (
        "fs.unlinkSync MUST appear AFTER the mismatch-401 return statement. "
        "If it appeared before, wrong-token attempts would delete the auth "
        "URL file — burning the URL on every failed attempt is hostile UX."
    )


# ───────────────────────────────────────────────────────────────────────
# D6 — factory-reset preservation (1 test)
# ───────────────────────────────────────────────────────────────────────


def test_factory_reset_route_preserves_dashboard_token():
    """D6 test 23 (Plan v1 §2) — AST/source-inspection of
    `app/api/factory-reset/route.ts::wipeAllFiles`; assert
    `.dashboard_token` is NOT in the deletion list literal AND a comment
    string referencing P0.S2 preservation exists.
    """
    src = _FACTORY_RESET_TS.read_text(encoding="utf-8")
    # 1. Preservation comment exists
    assert "P0.S2" in src, (
        "factory-reset route MUST contain P0.S2 preservation comment block "
        "naming the dashboard token preservation invariant"
    )
    assert "preservation" in src.lower() or "preserve" in src.lower(), (
        "preservation comment must explain WHY .dashboard_token survives wipe"
    )

    # 2. .dashboard_token MUST NOT appear as an ACTUAL filesToDelete entry.
    # Strip line-comments before scanning so the preservation-comment block
    # (which legitimately names .dashboard_token in its rationale text)
    # doesn't trigger a false positive.
    arr_start = src.find("filesToDelete = [")
    assert arr_start > 0, "wipeAllFiles MUST contain filesToDelete array"
    arr_end = src.find("]", arr_start)
    arr_body = src[arr_start:arr_end]
    # Remove line comments (// ...)
    arr_body_no_comments = re.sub(r"//[^\n]*", "", arr_body)
    assert ".dashboard_token" not in arr_body_no_comments, (
        "filesToDelete list (excluding comments) MUST NOT contain "
        ".dashboard_token entry (P0.S2 invariant)"
    )
    assert ".dashboard_auth_url" not in arr_body_no_comments, (
        "filesToDelete list (excluding comments) MUST NOT contain "
        ".dashboard_auth_url entry (P0.S2 invariant)"
    )

    # 3. The jpg-loop doesn't sweep dot-files (sanity — `.jpg` filter is exclusive)
    jpg_loop_idx = src.find("endsWith('.jpg')")
    if jpg_loop_idx < 0:
        jpg_loop_idx = src.find('endsWith(".jpg")')
    assert jpg_loop_idx > 0, "sanity: jpg-loop should be present (Wave 7)"
