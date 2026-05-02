import { NextRequest, NextResponse } from 'next/server'
import fs from 'fs'
import path from 'path'

export async function GET(req: NextRequest) {
  const photoPath = req.nextUrl.searchParams.get('path')
  if (!photoPath) return new NextResponse('Missing path', { status: 400 })

  // Security: only serve files from the faces/ directory
  const facesDir = path.resolve(path.join(process.cwd(), '..', 'faces'))
  const resolved = path.resolve(photoPath)
  if (!resolved.startsWith(facesDir)) {
    return new NextResponse('Forbidden', { status: 403 })
  }

  let data: Buffer
  try {
    data = fs.readFileSync(resolved)
  } catch {
    return new NextResponse('Not found', { status: 404 })
  }
  return new NextResponse(data, {
    headers: { 'Content-Type': 'image/jpeg', 'Cache-Control': 'public, max-age=3600' }
  })
}
