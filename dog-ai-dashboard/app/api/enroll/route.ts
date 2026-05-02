import { NextRequest, NextResponse } from 'next/server'
import fs from 'fs'
import path from 'path'
import { isBestFriendEnrolled } from '@/lib/db'

const FACES_DIR        = path.join(process.cwd(), '..', 'faces')
const ENROLL_REQUEST   = path.join(FACES_DIR, 'enroll_request.json')
const ENROLL_RESULT    = path.join(FACES_DIR, 'enroll_result.json')
const POLL_INTERVAL_MS = 500
const TIMEOUT_MS       = 40_000

export async function POST(req: NextRequest) {
  // Only allow enrollment if best friend is not yet enrolled
  if (isBestFriendEnrolled()) {
    return NextResponse.json(
      { error: 'Best friend already enrolled. No further manual enrollment allowed.' },
      { status: 403 }
    )
  }

  const { name } = await req.json()
  if (!name?.trim()) {
    return NextResponse.json({ error: 'Name is required' }, { status: 400 })
  }
  const safeName = name.trim().replace(/[^a-zA-Z0-9 ]/g, '').slice(0, 50)

  try { fs.unlinkSync(ENROLL_RESULT) } catch { /* ok */ }

  fs.writeFileSync(
    ENROLL_REQUEST,
    JSON.stringify({ name: safeName, role: 'best_friend', requested_at: Date.now() / 1000 })
  )

  const deadline = Date.now() + TIMEOUT_MS
  while (Date.now() < deadline) {
    await new Promise(r => setTimeout(r, POLL_INTERVAL_MS))
    if (fs.existsSync(ENROLL_RESULT)) {
      try {
        const result = JSON.parse(fs.readFileSync(ENROLL_RESULT, 'utf8'))
        fs.unlinkSync(ENROLL_RESULT)
        if (result.success) {
          return NextResponse.json({ success: true, name: result.name ?? safeName })
        }
        return NextResponse.json({ error: result.error ?? 'Enrollment failed' }, { status: 500 })
      } catch { /* not yet fully written */ }
    }
  }

  try { fs.unlinkSync(ENROLL_REQUEST) } catch {}
  return NextResponse.json(
    { error: 'Pipeline did not respond. Is it running?' },
    { status: 504 }
  )
}
