'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { ChevronLeft, Camera, CheckCircle, AlertCircle, Loader, Lock, Crown } from 'lucide-react'

type Step = 'loading' | 'locked' | 'idle' | 'capturing' | 'processing' | 'success' | 'error'

export default function EnrollPage() {
  const [name, setName]       = useState('')
  const [step, setStep]       = useState<Step>('loading')
  const [message, setMessage] = useState('')
  const [countdown, setCountdown] = useState(0)
  const [bfName, setBfName]   = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/best-friend')
      .then(r => r.json())
      .then(data => {
        if (data.enrolled) {
          setBfName(data.name)
          setStep('locked')
        } else {
          setStep('idle')
        }
      })
      .catch(() => setStep('idle'))
  }, [])

  const handleEnroll = async () => {
    if (!name.trim()) return

    setStep('capturing')
    setCountdown(5)

    for (let i = 4; i >= 0; i--) {
      await new Promise(r => setTimeout(r, 1000))
      setCountdown(i)
    }

    setStep('processing')
    setMessage('Saving face data...')

    try {
      const res  = await fetch('/api/enroll', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ name: name.trim() }),
      })
      const data = await res.json()

      if (res.ok) {
        setStep('success')
        setMessage(`${name.trim()} enrolled as best friend.`)
      } else {
        setStep('error')
        setMessage(data.error || 'Enrollment failed.')
      }
    } catch {
      setStep('error')
      setMessage('Network error. Is the pipeline running?')
    }
  }

  return (
    <div className="min-h-screen bg-night">
      <header className="border-b border-rail px-8 py-5 flex items-center">
        <div className="flex items-center gap-4">
          <Link href="/" className="flex items-center gap-2 text-dim hover:text-white transition-colors text-xs tracking-widest">
            <ChevronLeft size={14} />
            BACK
          </Link>
          <span className="text-rail">|</span>
          <span className="font-display text-sm font-bold tracking-widest">ENROLL BEST FRIEND</span>
        </div>
      </header>

      <main className="px-8 py-16 max-w-lg mx-auto">

        {step === 'loading' && (
          <div className="text-center py-8">
            <Loader size={24} className="text-dim mx-auto animate-spin" />
          </div>
        )}

        {step === 'locked' && (
          <div className="text-center py-12">
            <div className="w-16 h-16 border border-yellow-400/40 rounded-sm flex items-center justify-center mx-auto mb-6">
              <Crown size={28} className="text-yellow-400" />
            </div>
            <p className="font-display text-xl font-bold text-yellow-400 tracking-wider mb-3">
              BEST FRIEND ENROLLED
            </p>
            <p className="text-white font-semibold mb-2">{bfName?.toUpperCase()}</p>
            <p className="text-dim text-sm leading-relaxed max-w-sm mx-auto mt-4">
              The best friend slot is filled. Everyone else is enrolled automatically when they interact with the system.
            </p>
            <Link href="/people">
              <button className="mt-8 border border-acid/40 text-acid text-xs tracking-widest px-6 py-2 rounded-sm hover:border-acid transition-colors">
                VIEW ALL PEOPLE
              </button>
            </Link>
          </div>
        )}

        {step === 'idle' && (
          <div>
            <div className="border border-yellow-400/20 bg-yellow-400/5 rounded-sm p-4 mb-10 flex items-start gap-3">
              <Crown size={16} className="text-yellow-400 mt-0.5 shrink-0" />
              <div>
                <p className="text-yellow-400 text-xs font-bold tracking-wider">ONE-TIME ENROLLMENT</p>
                <p className="text-dim text-xs mt-1 leading-relaxed">
                  This can only be done once. After enrolling your best friend, all other people are enrolled automatically when they talk to the system.
                </p>
              </div>
            </div>

            <p className="text-dim text-xs tracking-widest mb-8">BEST FRIEND NAME</p>

            <div className="space-y-6">
              <input
                type="text"
                value={name}
                onChange={e => setName(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && name.trim() && handleEnroll()}
                placeholder="Enter name..."
                className="w-full bg-rail border border-muted rounded-sm px-4 py-3 text-white text-sm placeholder:text-rail focus:outline-none focus:border-yellow-400/60 transition-colors font-mono"
                autoFocus
              />

              <div className="border border-dashed border-rail rounded-sm p-8 text-center">
                <Camera size={24} className="text-rail mx-auto mb-3" />
                <p className="text-dim text-xs tracking-wider">LIVE CAMERA CAPTURE</p>
                <p className="text-rail text-xs mt-1">System will capture 20 frames over 6 seconds</p>
              </div>

              <button
                onClick={handleEnroll}
                disabled={!name.trim()}
                className="w-full py-3 bg-yellow-400/10 hover:bg-yellow-400/20 border border-yellow-400/40 hover:border-yellow-400 text-yellow-400 font-display font-semibold text-sm tracking-widest rounded-sm transition-all disabled:opacity-30 disabled:cursor-not-allowed"
              >
                ENROLL AS BEST FRIEND
              </button>
            </div>
          </div>
        )}

        {step === 'capturing' && (
          <div className="text-center py-8">
            <div className="relative w-32 h-32 mx-auto mb-8">
              <div className="absolute inset-0 border-2 border-yellow-400/20 rounded-full animate-ping" />
              <div className="absolute inset-2 border-2 border-yellow-400/40 rounded-full animate-pulse" />
              <div className="absolute inset-0 flex items-center justify-center">
                <span className="font-display text-5xl font-bold text-yellow-400">
                  {countdown}
                </span>
              </div>
            </div>
            <p className="font-display text-xl font-semibold text-white tracking-wider">
              LOOK AT CAMERA
            </p>
            <p className="text-dim text-xs mt-2 tracking-widest">
              CAPTURING <span className="text-white">{name.toUpperCase()}</span>
            </p>
          </div>
        )}

        {step === 'processing' && (
          <div className="text-center py-8">
            <Loader size={32} className="text-yellow-400 mx-auto mb-6 animate-spin" />
            <p className="font-display text-lg font-semibold tracking-wider">PROCESSING</p>
            <p className="text-dim text-xs mt-2">{message}</p>
          </div>
        )}

        {step === 'success' && (
          <div className="text-center py-8">
            <Crown size={40} className="text-yellow-400 mx-auto mb-6" />
            <p className="font-display text-xl font-bold text-yellow-400 tracking-wider">ENROLLED</p>
            <p className="text-dim text-sm mt-3 leading-relaxed">{message}</p>
            <Link href="/people">
              <button className="mt-8 border border-acid/40 text-acid text-xs tracking-widest px-6 py-2 rounded-sm hover:border-acid transition-colors">
                VIEW ALL PEOPLE
              </button>
            </Link>
          </div>
        )}

        {step === 'error' && (
          <div className="text-center py-8">
            <AlertCircle size={40} className="text-red-400 mx-auto mb-6" />
            <p className="font-display text-xl font-bold text-red-400 tracking-wider">FAILED</p>
            <p className="text-dim text-sm mt-3">{message}</p>
            <button
              onClick={() => { setStep('idle'); setName(''); setMessage('') }}
              className="mt-8 border border-rail text-dim text-xs tracking-widest px-6 py-2 rounded-sm hover:border-muted hover:text-white transition-colors"
            >
              TRY AGAIN
            </button>
          </div>
        )}
      </main>
    </div>
  )
}
