import { NextRequest, NextResponse } from 'next/server'
import fs from 'fs'
import path from 'path'

const FACES_DIR          = path.join(process.cwd(), '..', 'faces')
const STATE_PATH         = path.join(FACES_DIR, 'state.json')
const RESET_REQUEST_PATH = path.join(FACES_DIR, 'reset_request.json')
const RESET_RESULT_PATH  = path.join(FACES_DIR, 'reset_result.json')

// Files and directories to delete during a factory reset.
// Mirrors the logic in core/db.py wipe_all() — done here in Node.js so we
// don't need to shell out to Python when the pipeline is offline.
function wipeAllFiles(): void {
  const filesToDelete = [
    path.join(FACES_DIR, 'faces.db'),
    path.join(FACES_DIR, 'faces.db-shm'),
    path.join(FACES_DIR, 'faces.db-wal'),
    path.join(FACES_DIR, 'faiss.index'),
    path.join(FACES_DIR, 'memory.db'),
    path.join(FACES_DIR, 'memory.db-shm'),
    path.join(FACES_DIR, 'memory.db-wal'),
    path.join(FACES_DIR, 'brain.db'),
    path.join(FACES_DIR, 'brain.db-shm'),
    path.join(FACES_DIR, 'brain.db-wal'),
    path.join(FACES_DIR, 'state.json'),
    path.join(FACES_DIR, 'enroll_request.json'),
    path.join(FACES_DIR, 'enroll_result.json'),
    path.join(FACES_DIR, 'reset_request.json'),
    path.join(FACES_DIR, 'reset_result.json'),
  ]

  for (const f of filesToDelete) {
    try { fs.unlinkSync(f) } catch {}
  }

  // brain_graph/ — Kuzu property graph directory
  const graphDir = path.join(FACES_DIR, 'brain_graph')
  try { fs.rmSync(graphDir, { recursive: true, force: true }) } catch {}

  // memory_vectors/ (LanceDB directory)
  const vectorsDir = path.join(FACES_DIR, 'memory_vectors')
  try { fs.rmSync(vectorsDir, { recursive: true, force: true }) } catch {}

  // sim_session_state.json lives one level above faces/ (project root)
  const simState = path.join(FACES_DIR, '..', 'sim_session_state.json')
  try { fs.unlinkSync(simState) } catch {}

  // Delete all *.jpg photos
  try {
    const files = fs.readdirSync(FACES_DIR)
    for (const f of files) {
      if (f.endsWith('.jpg')) {
        try { fs.unlinkSync(path.join(FACES_DIR, f)) } catch {}
      }
    }
  } catch {}
}

function isPipelineLive(): boolean {
  try {
    if (!fs.existsSync(STATE_PATH)) return false
    const data = JSON.parse(fs.readFileSync(STATE_PATH, 'utf8'))
    return (Date.now() / 1000 - (data.updated_at || 0)) < 10
  } catch {
    return false
  }
}

export async function POST(req: NextRequest) {
  let body: { confirm?: string } = {}
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ error: 'Invalid JSON' }, { status: 400 })
  }

  if (body.confirm !== 'RESET') {
    return NextResponse.json(
      { error: 'Confirmation required. Send { "confirm": "RESET" }' },
      { status: 400 }
    )
  }

  // Ensure faces/ dir exists (pipeline may never have run yet)
  fs.mkdirSync(FACES_DIR, { recursive: true })

  if (!isPipelineLive()) {
    // Pipeline is offline — wipe files directly from Node.js (no Python needed)
    try {
      wipeAllFiles()
      return NextResponse.json({ success: true, note: 'pipeline_was_offline' })
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      return NextResponse.json({ error: `Reset failed: ${msg}` }, { status: 500 })
    }
  }

  // Pipeline is live — use request/result file IPC (same pattern as enroll)
  try { fs.unlinkSync(RESET_RESULT_PATH) } catch {}

  fs.writeFileSync(
    RESET_REQUEST_PATH,
    JSON.stringify({ requested_at: Date.now() / 1000 })
  )

  // Poll for result — 15s timeout, 500ms intervals
  const deadline = Date.now() + 15_000
  while (Date.now() < deadline) {
    await new Promise(r => setTimeout(r, 500))
    if (fs.existsSync(RESET_RESULT_PATH)) {
      try {
        const result = JSON.parse(fs.readFileSync(RESET_RESULT_PATH, 'utf8'))
        try { fs.unlinkSync(RESET_RESULT_PATH) } catch {}
        if (result.success) {
          return NextResponse.json({ success: true })
        }
        return NextResponse.json({ error: 'Reset partially failed — check pipeline logs' }, { status: 500 })
      } catch {
        return NextResponse.json({ error: 'Could not read reset result' }, { status: 500 })
      }
    }
  }

  // Timed out — clean up request file so pipeline doesn't trigger a late reset
  try { fs.unlinkSync(RESET_REQUEST_PATH) } catch {}
  return NextResponse.json(
    { error: 'Timed out waiting for pipeline to confirm reset' },
    { status: 504 }
  )
}
