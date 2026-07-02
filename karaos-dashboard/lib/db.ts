import Database from 'better-sqlite3'
import path from 'path'
import fs from 'fs'

const DB_PATH       = path.join(process.cwd(), '..', 'faces', 'faces.db')
const BRAIN_DB_PATH = path.join(process.cwd(), '..', 'faces', 'brain.db')
const STATE_PATH    = path.join(process.cwd(), '..', 'faces', 'state.json')

function getDb() {
  if (!fs.existsSync(DB_PATH)) return null
  return new Database(DB_PATH, { readonly: true })
}

function getBrainDb() {
  if (!fs.existsSync(BRAIN_DB_PATH)) return null
  return new Database(BRAIN_DB_PATH, { readonly: true })
}

export function getShadowPersons() {
  const db = getBrainDb()
  if (!db) return []
  try {
    const rows = db.prepare(`
      SELECT shadow_id, known_name, enrollment_status, facts, first_mentioned, last_mentioned
      FROM shadow_persons
      WHERE enrollment_status = 'pending'
      ORDER BY last_mentioned DESC
    `).all() as Array<{
      shadow_id: string; known_name: string; enrollment_status: string
      facts: string; first_mentioned: number; last_mentioned: number
    }>
    return rows.map(r => ({
      shadow_id:         r.shadow_id,
      known_name:        r.known_name,
      enrollment_status: r.enrollment_status,
      fact_count:        (() => { try { return (JSON.parse(r.facts || '[]') as unknown[]).length } catch { return 0 } })(),
      first_mentioned:   r.first_mentioned,
      last_mentioned:    r.last_mentioned,
    }))
  } finally {
    db.close()
  }
}

export function getPeople() {
  const db = getDb()
  if (!db) return []
  try {
    return db.prepare(`
      SELECT p.id, p.name, p.enrolled_at, p.last_seen, p.photo_path,
             p.person_type,
             COUNT(e.id) as embedding_count,
             COUNT(DISTINCT ve.id) as voice_count
      FROM persons p
      LEFT JOIN embeddings e ON e.person_id = p.id
      LEFT JOIN voice_embeddings ve ON ve.person_id = p.id
      GROUP BY p.id
      ORDER BY COALESCE(p.last_seen, p.enrolled_at) DESC
    `).all()
  } finally {
    db.close()
  }
}

export function getPerson(id: string) {
  const db = getDb()
  if (!db) return null
  try {
    return db.prepare('SELECT * FROM persons WHERE id = ?').get(id)
  } finally {
    db.close()
  }
}

export function getBestFriend(): { id: string; name: string; enrolled_at: number } | null {
  const db = getDb()
  if (!db) return null
  try {
    return (db.prepare(
      `SELECT id, name, enrolled_at FROM persons WHERE person_type = 'best_friend' LIMIT 1`
    ).get() as { id: string; name: string; enrolled_at: number } | undefined) ?? null
  } finally {
    db.close()
  }
}

export function isBestFriendEnrolled(): boolean {
  return getBestFriend() !== null
}

export function getState() {
  try {
    if (!fs.existsSync(STATE_PATH)) {
      return { online: false, mode: 'offline', status: 'offline' }
    }
    const data = JSON.parse(fs.readFileSync(STATE_PATH, 'utf8'))
    const stale = Date.now() / 1000 - (data.updated_at || 0) > 10
    return { ...data, online: !stale }
  } catch {
    return { online: false, mode: 'offline', status: 'offline' }
  }
}
