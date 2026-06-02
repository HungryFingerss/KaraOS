import { NextRequest, NextResponse } from 'next/server'
import { getBestFriend } from '@/lib/db'
import { requireAuth } from '@/lib/requireAuth'

export async function GET(req: NextRequest) {
  const denied = requireAuth(req); if (denied) return denied
  const bf = getBestFriend()
  return NextResponse.json({
    enrolled: bf !== null,
    name:     bf?.name ?? null,
    enrolled_at: bf?.enrolled_at ?? null,
  })
}
