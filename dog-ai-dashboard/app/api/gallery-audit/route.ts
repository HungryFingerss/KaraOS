import { NextRequest, NextResponse } from 'next/server'
import { execFile } from 'child_process'
import path from 'path'

// Audit all enrolled persons — returns array of audit results (JSON from audit_person.py --all)
export async function GET(_req: NextRequest) {
  const scriptPath = path.join(process.cwd(), '..', 'audit_person.py')
  const pythonPath = process.env.PYTHON_PATH || 'python'

  return new Promise<NextResponse>((resolve) => {
    execFile(
      pythonPath,
      [scriptPath, '--all', '--json'],
      { cwd: path.join(process.cwd(), '..') },
      (error, stdout, stderr) => {
        if (error) {
          console.error('[GalleryAudit] Failed:', stderr || error.message)
          resolve(NextResponse.json({ error: 'Audit failed' }, { status: 500 }))
          return
        }
        try {
          const results = JSON.parse(stdout)
          resolve(NextResponse.json(results))
        } catch {
          console.error('[GalleryAudit] JSON parse error:', stdout)
          resolve(NextResponse.json({ error: 'Invalid audit output' }, { status: 500 }))
        }
      }
    )
  })
}
