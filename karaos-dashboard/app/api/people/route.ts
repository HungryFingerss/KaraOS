import { NextRequest, NextResponse } from 'next/server'
import { getPeople, getBestFriend } from '@/lib/db'
import { requireAuth } from '@/lib/requireAuth'

export async function GET(req: NextRequest) {
  const denied = requireAuth(req); if (denied) return denied
  const people = getPeople()
  const bf     = getBestFriend()
  return NextResponse.json({
    people,
    total: people.length,
    best_friend_enrolled: bf !== null,
    best_friend_name: bf?.name ?? null,
  })
}
