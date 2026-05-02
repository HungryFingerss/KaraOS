import { NextResponse } from 'next/server'
import { getBestFriend } from '@/lib/db'

export async function GET() {
  const bf = getBestFriend()
  return NextResponse.json({
    enrolled: bf !== null,
    name:     bf?.name ?? null,
    enrolled_at: bf?.enrolled_at ?? null,
  })
}
