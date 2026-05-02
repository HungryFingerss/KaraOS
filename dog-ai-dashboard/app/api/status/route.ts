import { NextResponse } from 'next/server'
import { getState } from '@/lib/db'

export async function GET() {
  return NextResponse.json(getState())
}
