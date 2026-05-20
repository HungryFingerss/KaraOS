// dog-ai-dashboard/middleware.ts — P0.S2 dashboard authentication gate
//
// Gates every `/api/*` route except `/api/auth` (the one-shot validation
// endpoint that mints the session cookie). Reads `.dashboard_token` from
// the parent `faces/` directory on every request — NO module-scope cache —
// so manual token replacement / corruption recovery is reflected without
// a server restart (Plan v1 D4 file-read invariant).
//
// Comparison uses constant-time `crypto.timingSafeEqual` after a length-
// equality pre-check (length-equal-then-timingsafe-equal is the locked
// pattern per Plan v1 §2 D2 test 8; bare === would short-circuit on first
// differing byte → timing-attack surface).
//
// Auth failures return 401 JSON `{error: "Unauthorized"}`. Missing token
// file on disk returns 401 JSON `{error: "Pipeline not started — token
// not yet generated"}` so the operator can distinguish "browser bad
// cookie" from "pipeline never booted to publish the token."
//
// Spec: tests/p0_s2_plan_v2.md §12 Phase 2.

import { NextRequest, NextResponse } from 'next/server'
import fs from 'fs'
import path from 'path'
import crypto from 'crypto'

// Resolve faces/.dashboard_token at request time (NOT at module load) so
// tests can monkey-patch the working directory and so manual edits to
// the token file are picked up without a server restart.
function _tokenPath(): string {
  return path.join(process.cwd(), '..', 'faces', '.dashboard_token')
}

// Constant-time equality with explicit length pre-check. Per Plan v1
// §2 D2 test 8: bare `===` is a timing-attack surface; timingSafeEqual
// requires same-length buffers (throws otherwise), so check length first
// to short-circuit on the trivially-wrong case without timing leak.
function _safeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false
  return crypto.timingSafeEqual(Buffer.from(a, 'utf8'), Buffer.from(b, 'utf8'))
}

export function middleware(req: NextRequest) {
  // Inline allowlist — `/api/auth` is the only un-gated route because
  // it's the entry point that mints the session cookie. Keep this check
  // BEFORE any token-file I/O so the auth route works even when the
  // token file is being rotated (rename window is atomic but fs is fs).
  if (req.nextUrl.pathname === '/api/auth') {
    return NextResponse.next()
  }

  // Read the token file fresh on every request.
  let fileToken: string
  try {
    fileToken = fs.readFileSync(_tokenPath(), 'utf8').replace(/[\r\n]+$/, '')
  } catch (e: unknown) {
    // ENOENT = pipeline hasn't booted yet (token not generated). Other
    // errors (EACCES on Windows + corrupt ACL) also fail closed. Emit a
    // distinguishable 401 so the operator can tell apart "no token"
    // from "wrong cookie".
    return NextResponse.json(
      { error: 'Pipeline not started — token not yet generated' },
      { status: 401 }
    )
  }

  // Extract cookie value. Next.js Edge runtime parses cookies via the
  // request cookies API; the cookie name is the locked `dogai_session`
  // (Plan v1 §1.D2). Absent cookie → 401.
  const cookieValue = req.cookies.get('dogai_session')?.value
  if (!cookieValue) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  // Constant-time compare. Length pre-check + timingSafeEqual.
  if (!_safeEqual(cookieValue, fileToken)) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  // Authenticated — pass through.
  return NextResponse.next()
}

// Matcher — every `/api/*` route. The /api/auth allowlist is enforced
// inside the middleware body above so the matcher stays simple and
// future routes are gated by default.
export const config = {
  matcher: ['/api/:path*'],
}
