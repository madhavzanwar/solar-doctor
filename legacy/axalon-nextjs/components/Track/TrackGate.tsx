'use client'

import { useEffect, useState, type ReactNode } from 'react'
import { Lock } from 'lucide-react'
import { api, ApiError } from '@/lib/api'

// Only an unlock FLAG is stored client-side — the password itself is verified
// by the backend (Supabase app_config, or AXALON_TRACK_PASSWORD env override)
// and never persisted here.
const UNLOCK_FLAG = 'axalon_track_unlocked'

export function TrackGate({ children }: { children: ReactNode }) {
  const [isUnlocked, setIsUnlocked] = useState(false)
  const [isChecking, setIsChecking] = useState(true)
  // 'login' once a password exists; 'setup' the first time none is configured.
  const [mode, setMode] = useState<'login' | 'setup'>('login')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')
  const [isBusy, setIsBusy] = useState(false)

  useEffect(() => {
    setIsUnlocked(sessionStorage.getItem(UNLOCK_FLAG) === '1')
    setIsChecking(false)
  }, [])

  function unlock() {
    sessionStorage.setItem(UNLOCK_FLAG, '1')
    setPassword('')
    setConfirm('')
    setIsUnlocked(true)
  }

  async function submitLogin() {
    if (!password) {
      setError('Enter the workspace password')
      return
    }
    setIsBusy(true)
    setError('')
    try {
      await api.trackLogin(password)
      unlock()
    } catch (err) {
      // 503 = no password set yet → switch to first-time setup.
      if (err instanceof ApiError && err.status === 503) {
        setMode('setup')
        setError('')
        setPassword('')
      } else if (err instanceof ApiError && err.status === 0) {
        setError("Can't reach the server — the backend may still be starting.")
      } else if (err instanceof ApiError && err.status === 401) {
        setError('Wrong password')
      } else {
        setError(err instanceof Error ? err.message : 'Login failed')
      }
    } finally {
      setIsBusy(false)
    }
  }

  async function submitSetup() {
    if (password.length < 6) {
      setError('Password must be at least 6 characters')
      return
    }
    if (password !== confirm) {
      setError('Passwords do not match')
      return
    }
    setIsBusy(true)
    setError('')
    try {
      await api.setTrackPassword(password)
      await api.trackLogin(password)
      unlock()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not set password')
    } finally {
      setIsBusy(false)
    }
  }

  if (isChecking) return null
  if (isUnlocked) return <>{children}</>

  const isSetup = mode === 'setup'

  return (
    <div className="auth-gate">
      <div className="auth-gate-panel">
        <h2>
          <Lock size={16} /> {isSetup ? 'Set workspace password' : 'Track workspace'}
        </h2>
        <p>
          {isSetup
            ? 'No password is set yet. Choose one to protect inventory, prototypes, orders, and files.'
            : 'Inventory, prototypes, orders, research — enter the workspace password.'}
        </p>
        <input
          type="password"
          autoFocus
          placeholder={isSetup ? 'New password (min 6 chars)' : 'Password'}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && !isSetup && submitLogin()}
        />
        {isSetup && (
          <input
            type="password"
            placeholder="Confirm password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && submitSetup()}
          />
        )}
        {error && <p className="auth-gate-error">{error}</p>}
        <button type="button" disabled={isBusy} onClick={isSetup ? submitSetup : submitLogin}>
          {isBusy ? 'Working…' : isSetup ? 'Set password & enter' : 'Unlock'}
        </button>
      </div>
    </div>
  )
}
