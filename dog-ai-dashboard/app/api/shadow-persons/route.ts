import { NextRequest, NextResponse } from 'next/server'
import { getShadowPersons } from '@/lib/db'
import { requireAuth } from '@/lib/requireAuth'

export async function GET(req: NextRequest) {
  const denied = requireAuth(req); if (denied) return denied
  const shadows = getShadowPersons()
  return NextResponse.json({ shadows, total: shadows.length })
}
