'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { Trash2, ChevronLeft, User, Crown } from 'lucide-react'

interface Person {
  id: string
  name: string
  enrolled_at: number
  last_seen: number | null
  photo_path: string | null
  person_type: string
  embedding_count: number
  voice_count: number
}

interface ShadowPerson {
  shadow_id:         string
  known_name:        string
  enrollment_status: string
  fact_count:        number
  first_mentioned:   number
  last_mentioned:    number
}

const TYPE_CONFIG: Record<string, { label: string; color: string }> = {
  best_friend: { label: 'BEST FRIEND', color: 'text-yellow-400 border-yellow-400/40 bg-yellow-400/5' },
  known:       { label: 'KNOWN',       color: 'text-acid border-acid/40 bg-acid/5' },
  stranger:    { label: 'VISITOR',     color: 'text-dim border-rail bg-rail/30' },
}

export default function PeoplePage() {
  const [people, setPeople]     = useState<Person[]>([])
  const [shadows, setShadows]   = useState<ShadowPerson[]>([])
  const [loading, setLoading]   = useState(true)
  const [deleting, setDeleting] = useState<string | null>(null)
  const [confirm, setConfirm]   = useState<string | null>(null)

  const fetchPeople = async () => {
    try {
      const [res, shadowRes] = await Promise.all([
        fetch('/api/people'),
        fetch('/api/shadow-persons'),
      ])
      const data       = await res.json()
      const shadowData = await shadowRes.json()
      setPeople(data.people || [])
      setShadows(shadowData.shadows || [])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchPeople() }, [])

  const handleDelete = async (id: string) => {
    if (confirm !== id) {
      setConfirm(id)
      setTimeout(() => setConfirm(c => c === id ? null : c), 3000)
      return
    }
    setDeleting(id)
    setConfirm(null)
    try {
      await fetch(`/api/people/${id}`, { method: 'DELETE' })
      await fetchPeople()
    } finally {
      setDeleting(null)
    }
  }

  const formatDate = (ts: number | null) => {
    if (!ts) return '—'
    const d = new Date(ts * 1000)
    return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
  }

  const formatTime = (ts: number | null) => {
    if (!ts) return ''
    const d = new Date(ts * 1000)
    return d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: true })
  }

  const bestFriend = people.find(p => p.person_type === 'best_friend')
  const others     = people.filter(p => p.person_type !== 'best_friend')

  return (
    <div className="min-h-screen bg-night">
      <header className="border-b border-rail px-8 py-5 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link href="/" className="flex items-center gap-2 text-dim hover:text-white transition-colors text-xs tracking-widest">
            <ChevronLeft size={14} />
            BACK
          </Link>
          <span className="text-rail">|</span>
          <span className="font-display text-sm font-bold tracking-widest">ALL PEOPLE</span>
        </div>
      </header>

      <main className="px-8 py-10 max-w-4xl mx-auto">
        {loading ? (
          <div className="text-dim text-xs tracking-widest animate-pulse">LOADING...</div>
        ) : people.length === 0 ? (
          <div className="border border-dashed border-rail rounded-sm p-16 text-center">
            <User size={32} className="text-rail mx-auto mb-4" />
            <p className="text-dim text-sm tracking-wider">NO PEOPLE YET</p>
            <p className="text-rail text-xs mt-2">Start the pipeline and interact with the system</p>
          </div>
        ) : (
          <>
            <p className="text-dim text-xs tracking-widest mb-6">
              {people.length} PERSON{people.length !== 1 ? 'S' : ''} IN DATABASE
            </p>

            {/* Best friend first */}
            {bestFriend && (
              <div className="mb-6">
                <p className="text-xs text-yellow-400/60 tracking-widest mb-3 flex items-center gap-2">
                  <Crown size={10} />
                  BEST FRIEND
                </p>
                <PersonRow person={bestFriend} confirm={confirm} deleting={deleting}
                  onDelete={handleDelete} formatDate={formatDate} formatTime={formatTime} />
              </div>
            )}

            {others.length > 0 && (
              <div>
                {bestFriend && (
                  <p className="text-xs text-dim tracking-widest mb-3 mt-2">EVERYONE ELSE</p>
                )}
                <div className="space-y-2">
                  {others.map(person => (
                    <PersonRow key={person.id} person={person} confirm={confirm} deleting={deleting}
                      onDelete={handleDelete} formatDate={formatDate} formatTime={formatTime} />
                  ))}
                </div>
              </div>
            )}

            {shadows.length > 0 && (
              <div className="mt-8">
                <p className="text-xs text-violet-400/60 tracking-widest mb-3">
                  SHADOW PERSONS — MENTIONED BUT NOT ENROLLED
                </p>
                <div className="space-y-2">
                  {shadows.map(s => (
                    <ShadowRow key={s.shadow_id} shadow={s} formatDate={formatDate} />
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </main>
    </div>
  )
}

function PersonRow({
  person, confirm, deleting, onDelete, formatDate, formatTime
}: {
  person: Person
  confirm: string | null
  deleting: string | null
  onDelete: (id: string) => void
  formatDate: (ts: number | null) => string
  formatTime: (ts: number | null) => string
}) {
  const typeConf = TYPE_CONFIG[person.person_type] ?? TYPE_CONFIG.known
  const photoSrc = person.photo_path
    ? `/api/photo?path=${encodeURIComponent(person.photo_path)}`
    : null

  return (
    <div className="border border-rail hover:border-muted rounded-sm p-4 flex items-center gap-4 transition-colors group">
      {/* Avatar / photo */}
      <div className="w-12 h-12 rounded-sm border border-muted bg-rail flex items-center justify-center shrink-0 overflow-hidden">
        {photoSrc ? (
          <img src={photoSrc} alt={person.name} className="w-full h-full object-cover" />
        ) : (
          <span className="text-dim text-sm font-bold">
            {person.name.charAt(0).toUpperCase()}
          </span>
        )}
      </div>

      {/* Info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <p className="font-display font-semibold text-sm tracking-wider text-white">
            {person.name.toUpperCase()}
          </p>
          <span className={`text-[10px] px-2 py-0.5 rounded-sm border tracking-widest ${typeConf.color}`}>
            {typeConf.label}
          </span>
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          <span className="text-dim text-xs">
            {person.embedding_count} face{person.embedding_count !== 1 ? 's' : ''}
          </span>
          {person.voice_count > 0 && (
            <>
              <span className="text-rail text-xs">·</span>
              <span className="text-dim text-xs">{person.voice_count} voice</span>
            </>
          )}
          <span className="text-rail text-xs">·</span>
          <span className="text-dim text-xs">
            first seen {formatDate(person.enrolled_at)}
          </span>
          {person.last_seen && (
            <>
              <span className="text-rail text-xs">·</span>
              <span className="text-dim text-xs">
                last seen {formatDate(person.last_seen)} {formatTime(person.last_seen)}
              </span>
            </>
          )}
        </div>
      </div>

      {/* Delete */}
      <button
        onClick={() => onDelete(person.id)}
        disabled={deleting === person.id}
        className={`
          shrink-0 flex items-center gap-2 text-xs px-3 py-1.5 rounded-sm border transition-all
          ${confirm === person.id
            ? 'border-red-500/60 bg-red-500/10 text-red-400'
            : 'border-rail text-rail hover:border-red-500/40 hover:text-red-400 opacity-0 group-hover:opacity-100'
          }
        `}
      >
        <Trash2 size={12} />
        {confirm === person.id ? 'CONFIRM?' : 'DELETE'}
      </button>
    </div>
  )
}

function ShadowRow({
  shadow, formatDate
}: {
  shadow: ShadowPerson
  formatDate: (ts: number | null) => string
}) {
  return (
    <div className="border border-dashed border-rail/50 rounded-sm p-4 flex items-center gap-4 opacity-70">
      {/* Ghost avatar */}
      <div className="w-12 h-12 rounded-sm border border-dashed border-rail/50 bg-night flex items-center justify-center shrink-0">
        <span className="text-dim text-sm font-bold">
          {shadow.known_name.charAt(0).toUpperCase()}
        </span>
      </div>

      {/* Info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <p className="font-display font-semibold text-sm tracking-wider text-dim">
            {shadow.known_name.toUpperCase()}
          </p>
          <span className="text-[10px] px-2 py-0.5 rounded-sm border tracking-widest text-violet-400 border-violet-400/40 bg-violet-400/5">
            SHADOW
          </span>
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          <span className="text-dim text-xs">
            {shadow.fact_count} fact{shadow.fact_count !== 1 ? 's' : ''}
          </span>
          <span className="text-rail text-xs">·</span>
          <span className="text-dim text-xs">
            first mentioned {formatDate(shadow.first_mentioned)}
          </span>
          <span className="text-rail text-xs">·</span>
          <span className="text-dim text-xs">
            last mentioned {formatDate(shadow.last_mentioned)}
          </span>
        </div>
      </div>
    </div>
  )
}
