import { NextRequest, NextResponse } from 'next/server'
import { getState } from '@/lib/db'
import { requireAuth } from '@/lib/requireAuth'

export async function GET(req: NextRequest) {
  const denied = requireAuth(req); if (denied) return denied
  return NextResponse.json(getState())
}
