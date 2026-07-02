import { NextRequest, NextResponse } from 'next/server'
import { execFile } from 'child_process'
import path from 'path'
import { requireAuth } from '@/lib/requireAuth'

const PERSON_ID_RE = /^[a-zA-Z0-9_-]{1,80}$/

// GET /api/gallery-audit/[id] — audit a single person
export async function GET(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  const denied = requireAuth(req); if (denied) return denied
  const { id } = params
  if (!id || !PERSON_ID_RE.test(id)) {
    return NextResponse.json({ error: 'Invalid ID' }, { status: 400 })
  }

  const scriptPath = path.join(process.cwd(), '..', 'audit_person.py')
  const pythonPath = process.env.PYTHON_PATH || 'python'

  return new Promise<NextResponse>((resolve) => {
    execFile(
      pythonPath,
      [scriptPath, '--id', id, '--json'],
      { cwd: path.join(process.cwd(), '..') },
      (error, stdout, stderr) => {
        if (error) {
          console.error('[GalleryAudit] Failed:', stderr || error.message)
          resolve(NextResponse.json({ error: 'Audit failed' }, { status: 500 }))
          return
        }
        try {
          resolve(NextResponse.json(JSON.parse(stdout)))
        } catch {
          resolve(NextResponse.json({ error: 'Invalid audit output' }, { status: 500 }))
        }
      }
    )
  })
}

// DELETE /api/gallery-audit/[id] — repair (remove outliers) for a single person
export async function DELETE(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  const denied = requireAuth(req); if (denied) return denied
  const { id } = params
  if (!id || !PERSON_ID_RE.test(id)) {
    return NextResponse.json({ error: 'Invalid ID' }, { status: 400 })
  }

  const scriptPath = path.join(process.cwd(), '..', 'audit_person.py')
  const pythonPath = process.env.PYTHON_PATH || 'python'

  return new Promise<NextResponse>((resolve) => {
    execFile(
      pythonPath,
      [scriptPath, '--id', id, '--repair', '--json'],
      { cwd: path.join(process.cwd(), '..') },
      (error, stdout, stderr) => {
        if (error) {
          console.error('[GalleryAudit] Repair failed:', stderr || error.message)
          resolve(NextResponse.json({ error: 'Repair failed' }, { status: 500 }))
          return
        }
        try {
          resolve(NextResponse.json(JSON.parse(stdout)))
        } catch {
          resolve(NextResponse.json({ error: 'Invalid repair output' }, { status: 500 }))
        }
      }
    )
  })
}
