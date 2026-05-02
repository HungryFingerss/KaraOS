import { NextResponse } from 'next/server'
import { getShadowPersons } from '@/lib/db'

export async function GET() {
  const shadows = getShadowPersons()
  return NextResponse.json({ shadows, total: shadows.length })
}
