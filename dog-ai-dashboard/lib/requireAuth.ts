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
