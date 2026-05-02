'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { Users, Cpu, Eye, AlertCircle, ArrowRight, Trash2, Crown, Lock } from 'lucide-react'

interface Status {
  online: boolean
  mode: string
  current_person: string | null
  visible_people: string[]
  message: string
  updated_at: number
}

const MODE_LABEL: Record<string, string> = {
  watching: 'WATCHING',
  listening: 'LISTENING',
  speaking: 'SPEAKING',
  enrolling: 'ENROLLING',
  starting: 'STARTING',
  offline: 'OFFLINE',
}

const MODE_COLOR: Record<string, string> = {
  watching: 'text-dim',
  listening: 'text-acid',
  speaking: 'text-acid',
  enrolling: 'text-yellow-400',
  starting: 'text-dim',
  offline: 'text-red-500',
}

type ResetPhase = 'idle' | 'confirming' | 'resetting' | 'done' | 'error'

export default function Home() {
  const [status, setStatus] = useState<Status | null>(null)
  const [peopleCount, setPeopleCount] = useState<number>(0)
  const [bfEnrolled, setBfEnrolled] = useState<boolean>(false)
  const [bfName, setBfName] = useState<string | null>(null)
  const [tick, setTick] = useState(0)
  const [resetPhase, setResetPhase] = useState<ResetPhase>('idle')
  const [confirmText, setConfirmText] = useState('')
  const [resetMessage, setResetMessage] = useState('')

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const [s, p] = await Promise.all([
          fetch('/api/status').then(r => r.json()),
          fetch('/api/people').then(r => r.json()),
        ])
        setStatus(s)
        setPeopleCount(p.total || 0)
        setBfEnrolled(p.best_friend_enrolled || false)
        setBfName(p.best_friend_name || null)
      } catch { }
    }

    fetchStatus()
    const iv = setInterval(() => {
      fetchStatus()
      setTick(t => t + 1)
    }, 2000)
    return () => clearInterval(iv)
  }, [])

  const handleReset = async () => {
    if (confirmText !== 'RESET') return
    setResetPhase('resetting')
    try {
      const res = await fetch('/api/factory-reset', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ confirm: 'RESET' }),
      })
      const data = await res.json()
      if (res.ok) {
        setResetPhase('done')
        setResetMessage('All data wiped. System is brand new.')
        setPeopleCount(0)
        setBfEnrolled(false)
        setBfName(null)
        setTimeout(() => {
          setResetPhase('idle')
          setConfirmText('')
          setResetMessage('')
        }, 4000)
      } else {
        setResetPhase('error')
        setResetMessage(data.error || 'Reset failed.')
      }
    } catch {
      setResetPhase('error')
      setResetMessage('Network error — check pipeline logs.')
    }
  }

  const mode = status?.mode || 'offline'
  const isOnline = status?.online ?? false
  const modeLabel = MODE_LABEL[mode] || mode.toUpperCase()
  const modeColor = MODE_COLOR[mode] || 'text-dim'
  const isActive = mode === 'listening' || mode === 'speaking'

  return (
    <div className="min-h-screen bg-night relative overflow-hidden scanline">

      <div
        className="absolute inset-0 opacity-[0.03]"
        style={{
          backgroundImage: 'linear-gradient(#b8ff35 1px, transparent 1px), linear-gradient(90deg, #b8ff35 1px, transparent 1px)',
          backgroundSize: '48px 48px',
        }}
      />

      <header className="relative z-10 border-b border-rail px-8 py-5 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div className="w-8 h-8 border border-acid rounded-sm flex items-center justify-center glow-acid">
            <span className="text-acid text-xs font-bold">AI</span>
          </div>
          <span className="font-display text-lg font-bold tracking-widest text-white">
            DOG<span className="text-acid">·</span>AI
          </span>
        </div>

        <nav className="flex items-center gap-8 text-xs text-dim tracking-widest">
          <span className="text-white border-b border-acid pb-1">STATUS</span>
          <Link href="/people" className="hover:text-white transition-colors">PEOPLE</Link>
          <Link href="/enroll" className="hover:text-white transition-colors flex items-center gap-1">
            {bfEnrolled
              ? <><Lock size={9} className="text-yellow-400/60" /><span className="text-yellow-400/60">ENROLLED</span></>
              : 'ENROLL'
            }
          </Link>
        </nav>
      </header>

      <main className="relative z-10 px-8 py-12 max-w-5xl mx-auto">

        <div className="mb-16">
          <div className="flex items-start gap-6">
            <div className="mt-3">
              <div className={`w-3 h-3 rounded-full ${isOnline ? 'bg-acid' : 'bg-red-500'} ${isActive ? 'animate-pulse' : ''}`} />
            </div>

            <div>
              <p className="text-dim text-xs tracking-widest mb-2">SYSTEM STATUS</p>
              <h1 className={`font-display text-7xl font-bold tracking-tight ${modeColor} ${isActive ? 'text-glow-acid' : ''} transition-all duration-500`}>
                {modeLabel}
              </h1>

              {status?.current_person && (
                <p className="mt-4 text-dim text-sm tracking-wider">
                  WITH <span className="text-white font-bold">{status.current_person.toUpperCase()}</span>
                </p>
              )}

              {status?.message && mode === 'speaking' && (
                <p className="mt-3 text-sm text-acid max-w-md leading-relaxed">
                  "{status.message}"
                </p>
              )}
            </div>
          </div>
        </div>

        <div className="grid grid-cols-3 gap-4 mb-12">
          <StatCard
            icon={<Users size={16} />}
            label="ALL PEOPLE"
            value={peopleCount.toString()}
            sub="in database"
          />
          <StatCard
            icon={<Eye size={16} />}
            label="VISIBLE"
            value={(status?.visible_people?.length || 0).toString()}
            sub={status?.visible_people?.join(', ') || 'no one detected'}
          />
          <StatCard
            icon={<Cpu size={16} />}
            label="PIPELINE"
            value={isOnline ? 'LIVE' : 'OFF'}
            sub={isOnline ? `mode: ${mode}` : '.\venv\Scripts\python pipeline.py'}
            valueColor={isOnline ? 'text-acid' : 'text-red-400'}
          />
        </div>

        {/* Best friend status */}
        <div className={`mb-8 border rounded-sm p-4 flex items-center gap-3 ${bfEnrolled ? 'border-yellow-400/20 bg-yellow-400/5' : 'border-rail bg-rail/20'}`}>
          <Crown size={16} className={bfEnrolled ? 'text-yellow-400' : 'text-rail'} />
          <div>
            <p className={`text-xs font-bold tracking-wider ${bfEnrolled ? 'text-yellow-400' : 'text-dim'}`}>
              {bfEnrolled ? 'BEST FRIEND' : 'NO BEST FRIEND YET'}
            </p>
            <p className="text-dim text-xs mt-0.5">
              {bfEnrolled
                ? `${bfName?.toUpperCase()} — full access, memory, and personalization enabled`
                : 'Enroll your best friend to activate full memory and personalization'
              }
            </p>
          </div>
          {!bfEnrolled && (
            <Link href="/enroll" className="ml-auto shrink-0">
              <button className="border border-yellow-400/40 text-yellow-400 text-xs tracking-widest px-4 py-1.5 rounded-sm hover:border-yellow-400 transition-colors">
                ENROLL NOW
              </button>
            </Link>
          )}
        </div>

        {(status?.visible_people?.length ?? 0) > 0 && (
          <div className="mb-8 border border-rail rounded-sm p-6">
            <p className="text-xs text-dim tracking-widest mb-4">CURRENTLY VISIBLE</p>
            <div className="flex gap-3 flex-wrap">
              {status!.visible_people.map(name => (
                <span key={name} className="px-3 py-1.5 border border-acid/30 bg-acid/5 text-acid text-xs tracking-wider rounded-sm">
                  {name.toUpperCase()}
                </span>
              ))}
            </div>
          </div>
        )}

        <div className="grid grid-cols-2 gap-4">
          <Link href="/people">
            <div className="group border border-rail hover:border-acid/40 rounded-sm p-6 transition-all duration-200 hover:bg-rail/50 cursor-pointer">
              <div className="flex items-center justify-between mb-3">
                <Users size={18} className="text-dim group-hover:text-acid transition-colors" />
                <ArrowRight size={14} className="text-rail group-hover:text-dim transition-colors" />
              </div>
              <p className="font-display font-semibold text-sm tracking-wider">ALL PEOPLE</p>
              <p className="text-dim text-xs mt-1">Everyone who has interacted with the system</p>
            </div>
          </Link>

          <Link href="/enroll">
            <div className={`group border rounded-sm p-6 transition-all duration-200 cursor-pointer
              ${bfEnrolled
                ? 'border-yellow-400/20 bg-yellow-400/5 opacity-60 cursor-default'
                : 'border-rail hover:border-yellow-400/40 hover:bg-rail/50'
              }`}>
              <div className="flex items-center justify-between mb-3">
                {bfEnrolled
                  ? <Lock size={18} className="text-yellow-400/60" />
                  : <Crown size={18} className="text-dim group-hover:text-yellow-400 transition-colors" />
                }
                <ArrowRight size={14} className="text-rail group-hover:text-dim transition-colors" />
              </div>
              <p className="font-display font-semibold text-sm tracking-wider">
                {bfEnrolled ? 'BEST FRIEND ENROLLED' : 'ENROLL BEST FRIEND'}
              </p>
              <p className="text-dim text-xs mt-1">
                {bfEnrolled
                  ? `${bfName?.toUpperCase()} — slot filled`
                  : 'One-time enrollment — enables full personalization'
                }
              </p>
            </div>
          </Link>
        </div>

        {!isOnline && (
          <div className="mt-8 border border-red-500/20 bg-red-500/5 rounded-sm p-4 flex items-start gap-3">
            <AlertCircle size={16} className="text-red-400 mt-0.5 shrink-0" />
            <div>
              <p className="text-red-400 text-xs font-bold tracking-wider">PIPELINE OFFLINE</p>
              <p className="text-dim text-xs mt-1">Start the pipeline: <code className="text-white bg-rail px-1.5 py-0.5 rounded text-xs">python pipeline.py</code></p>
            </div>
          </div>
        )}

        <div className="mt-12 border-t border-rail pt-8">
          <button
            onClick={() => setResetPhase(p => p === 'idle' ? 'confirming' : 'idle')}
            className="flex items-center gap-2 text-xs text-dim tracking-widest hover:text-red-400 transition-colors"
          >
            <Trash2 size={12} />
            FACTORY RESET
          </button>

          {(resetPhase === 'confirming' || resetPhase === 'resetting' || resetPhase === 'error') && (
            <div className="mt-4 border border-red-500/30 bg-red-500/5 rounded-sm p-5 max-w-md">
              <p className="text-red-400 text-xs font-bold tracking-wider mb-1">DANGER ZONE</p>
              <p className="text-dim text-xs mb-4 leading-relaxed">
                This permanently deletes all enrolled faces, conversation memory, photos, and embeddings.
                The system will start completely fresh. This cannot be undone.
              </p>

              {resetPhase === 'error' && (
                <p className="text-red-400 text-xs mb-3">{resetMessage}</p>
              )}

              <input
                type="text"
                value={confirmText}
                onChange={e => setConfirmText(e.target.value.toUpperCase())}
                placeholder='Type RESET to confirm'
                disabled={resetPhase === 'resetting'}
                className="w-full bg-night border border-red-500/30 text-white text-xs px-3 py-2 rounded-sm mb-3 placeholder:text-dim focus:outline-none focus:border-red-500/60 disabled:opacity-50"
              />

              <button
                onClick={handleReset}
                disabled={confirmText !== 'RESET' || resetPhase === 'resetting'}
                className="w-full py-2 text-xs font-bold tracking-widest border border-red-500/60 bg-red-500/10 text-red-400 rounded-sm hover:bg-red-500/20 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
              >
                {resetPhase === 'resetting' ? 'WIPING...' : 'WIPE EVERYTHING'}
              </button>
            </div>
          )}

          {resetPhase === 'done' && (
            <div className="mt-4 border border-acid/30 bg-acid/5 rounded-sm p-4 max-w-md">
              <p className="text-acid text-xs font-bold tracking-wider">{resetMessage}</p>
            </div>
          )}
        </div>
      </main>
    </div>
  )
}

function StatCard({
  icon, label, value, sub, valueColor = 'text-white'
}: {
  icon: React.ReactNode
  label: string
  value: string
  sub: string
  valueColor?: string
}) {
  return (
    <div className="border border-rail rounded-sm p-5">
      <div className="flex items-center gap-2 text-dim mb-3">
        {icon}
        <span className="text-xs tracking-widest">{label}</span>
      </div>
      <p className={`font-display text-3xl font-bold ${valueColor}`}>{value}</p>
      <p className="text-dim text-xs mt-1 truncate">{sub}</p>
    </div>
  )
}
