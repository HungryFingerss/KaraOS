import { NextResponse } from 'next/server'
import { getPeople, getBestFriend } from '@/lib/db'

export async function GET() {
  const people = getPeople()
  const bf     = getBestFriend()
  return NextResponse.json({
    people,
    total: people.length,
    best_friend_enrolled: bf !== null,
    best_friend_name: bf?.name ?? null,
  })
}
