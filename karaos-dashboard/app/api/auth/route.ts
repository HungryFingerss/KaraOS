// karaos-dashboard/app/api/auth/route.ts — P0.S2 auth route (D2)
//
// GET /api/auth?token=<43-char-urlsafe> validates the token against the
// on-disk `.dashboard_token` (constant-time compare), on success sets the
// HttpOnly `karaos_session` cookie + 302-redirects to `/` + deletes the
// one-shot `.dashboard_auth_url` artifact. On failure: 401, no cookie,
// no URL delete.
//
// This route is the ONLY un-gated `/api/*` endpoint — middleware.ts
// inline-allowlists `/api/auth`. Validation reads from `.dashboard_token`
// (the source-of-truth), NEVER from `.dashboard_auth_url` (which is just
// the convenience artifact for the user's first click). Plan v2 §3.12
// locked: P4 invariant — `/api/auth` validates against `.dashboard_token`
// ONLY; `.dashboard_auth_url` delete is hygiene, NOT validation logic.
//
// Plan v2 §3.12 multi-tab idempotency: double-click of the auth URL
// returns 302 both times — the first call validates + deletes the URL
// file; the second call sees the URL file already gone (best-effort
// delete with try/catch ENOENT) but still validates against
// `.dashboard_token` and re-issues Set-Cookie (harmless).
//
// Spec: tests/p0_s2_plan_v2.md §12 Phase 2 + §3.12.

import { NextRequest, NextResponse } from 'next/server'
import fs from 'fs'
import path from 'path'
import crypto from 'crypto'

const FACES_DIR = path.join(process.cwd(), '..', 'faces')
const TOKEN_PATH = path.join(FACES_DIR, '.dashboard_token')
const AUTH_URL_PATH = path.join(FACES_DIR, '.dashboard_auth_url')

// Constant-time equality with explicit length pre-check (mirrors
// middleware.ts; same locked pattern per Plan v1 §2 D2 test 8).
function _safeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false
  return crypto.timingSafeEqual(Buffer.from(a, 'utf8'), Buffer.from(b, 'utf8'))
}

export async function GET(req: NextRequest) {
  // 1. Missing/empty `?token=` → 400 (distinct from 401 mismatch so
  //    operator can distinguish "user forgot the URL parameter" from
  //    "user has the wrong token").
  const tokenParam = req.nextUrl.searchParams.get('token')
  if (!tokenParam) {
    return NextResponse.json(
      { error: 'Missing token parameter' },
      { status: 400 }
    )
  }

  // 2. Read on-disk source-of-truth token. ENOENT → 401 (pipeline never
  //    booted) — same shape as middleware's "Pipeline not started" 401.
  let fileToken: string
  try {
    fileToken = fs.readFileSync(TOKEN_PATH, 'utf8').replace(/[\r\n]+$/, '')
  } catch {
    return NextResponse.json(
      { error: 'Pipeline not started — token not yet generated' },
      { status: 401 }
    )
  }

  // 3. Constant-time compare. Mismatch → 401, no cookie set, NO delete
  //    of `.dashboard_auth_url` (wrong attempts don't burn the URL).
  if (!_safeEqual(tokenParam, fileToken)) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  // 4. Validation success. Build the 302 redirect to root with cookie.
  //    Plan v1 §1.D2 locked cookie attributes: HttpOnly, SameSite=Strict,
  //    Path=/, Max-Age=315360000 (10 years — single-user localhost
  //    deployment; cookie rotation is via token rotation, not TTL).
  const redirectUrl = new URL('/', req.url)
  const res = NextResponse.redirect(redirectUrl, { status: 302 })
  res.cookies.set({
    name: 'karaos_session',
    value: fileToken,
    httpOnly: true,
    sameSite: 'strict',
    path: '/',
    maxAge: 315360000,
  })

  // 5. Delete the one-shot `.dashboard_auth_url` (best-effort,
  //    ENOENT-tolerant — Plan v2 §3.12 double-click idempotency:
  //    second click sees URL file already gone, validation still
  //    succeeds against `.dashboard_token`, re-issues Set-Cookie).
  try {
    fs.unlinkSync(AUTH_URL_PATH)
  } catch {
    // ENOENT (already deleted) or EACCES (Windows hold). Validation
    // path already succeeded; delete is purely hygiene per Plan v2 §3.12.
  }

  return res
}
