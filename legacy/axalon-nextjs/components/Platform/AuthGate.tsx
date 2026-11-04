'use client'

import {
  Fragment,
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type FormEvent,
  type ReactNode,
} from 'react'
import { QueryClientContext } from '@tanstack/react-query'
import { api, ApiError, CREDENTIAL_STORAGE_KEY, shareToken, type AuthMe, type AuthMode } from '@/lib/api'

// 'unknown' until /auth/mode answers (or when the API is unreachable) — treated
// exactly like the legacy key flow so off/apikey deployments never change.
type GateMode = AuthMode | 'unknown'

type AuthContextValue = {
  apiKey: string
  setApiKey: (key: string) => void
  mode: GateMode
  me: AuthMe | null
  /** False only for users-mode viewers and share links. The server enforces regardless. */
  canWrite: boolean
  /** Users-mode admin: may manage accounts and share links. */
  isAdmin: boolean
  logout: () => Promise<void>
}

const AuthCtx = createContext<AuthContextValue>({
  apiKey: '',
  setApiKey: () => {},
  mode: 'unknown',
  me: null,
  canWrite: true,
  isAdmin: false,
  logout: async () => {},
})

export function useApiKey() {
  const { apiKey, setApiKey } = useContext(AuthCtx)
  return { apiKey, setApiKey }
}

export function useAuth() {
  return useContext(AuthCtx)
}

/** Renders children only for callers allowed to change data. */
export function CanWrite({ children }: { children: ReactNode }) {
  return useAuth().canWrite ? <>{children}</> : null
}

function loginErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 401) return 'Invalid email or password'
    if (err.status === 429) return 'Too many attempts — wait a few minutes and try again'
    if (err.status === 0) return 'Cannot reach the server'
  }
  return 'Sign-in failed — try again'
}

export function AuthGate({ children }: { children: ReactNode }) {
  const [apiKey, setApiKeyState] = useState('')
  const [locked, setLocked] = useState(false)
  const [input, setInput] = useState('')
  const [error, setError] = useState('')
  const [mode, setMode] = useState<GateMode>('unknown')
  const [me, setMe] = useState<AuthMe | null>(null)
  // Bumped on sign-in/out so the console remounts and refetches with the new
  // credential instead of showing data (or 401s) from the previous one.
  const [epoch, setEpoch] = useState(0)
  // Optional: the gate also renders outside a QueryClientProvider (tests, and
  // any page that doesn't use react-query).
  const queryClient = useContext(QueryClientContext)

  useEffect(() => {
    const stored = sessionStorage.getItem(CREDENTIAL_STORAGE_KEY)
    const envKey = process.env.NEXT_PUBLIC_AXALON_API_KEY ?? ''
    const key = stored ?? envKey
    if (key) {
      sessionStorage.setItem(CREDENTIAL_STORAGE_KEY, key)
      setApiKeyState(key)
    }
    // No key: stay unlocked — keyless backends (dev/CI) just work, and a
    // protected backend triggers 'axalon:unauthorized' on the first 401.

    let cancelled = false
    api
      .authMode()
      .then(async ({ mode: serverMode }) => {
        if (cancelled) return
        setMode(serverMode === 'users' || serverMode === 'apikey' || serverMode === 'off' ? serverMode : 'unknown')
        if (serverMode !== 'users') return
        try {
          const current = await api.me()
          if (cancelled) return
          setMe(current)
          // A console request may have 401'd before the session was confirmed.
          setLocked(false)
        } catch {
          if (!cancelled) setLocked(true)
        }
      })
      .catch(() => {
        if (!cancelled) setMode('unknown')
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    function onUnauthorized() {
      setLocked(true)
    }
    window.addEventListener('axalon:unauthorized', onUnauthorized)
    return () => window.removeEventListener('axalon:unauthorized', onUnauthorized)
  }, [])

  const setApiKey = useCallback((key: string) => {
    sessionStorage.setItem(CREDENTIAL_STORAGE_KEY, key)
    setApiKeyState(key)
  }, [])

  const logout = useCallback(async () => {
    try {
      await api.logout()
    } catch {
      /* the session is dropped locally either way */
    }
    sessionStorage.removeItem(CREDENTIAL_STORAGE_KEY)
    setApiKeyState('')
    setMe(null)
    setLocked(true)
    // Cached responses belong to the account that fetched them.
    queryClient?.clear()
    setEpoch((n) => n + 1)
  }, [queryClient])

  function submitKey() {
    const trimmed = input.trim()
    if (!trimmed) {
      setError('Enter a key')
      return
    }
    setApiKey(trimmed)
    setLocked(false)
    setError('')
    setInput('')
    // Same data, new credential: refetch what 401'd (or was served) without it.
    void queryClient?.invalidateQueries()
  }

  const onSignedIn = useCallback(
    (token: string, signedIn: AuthMe) => {
      setApiKey(token)
      setMe(signedIn)
      setLocked(false)
      queryClient?.clear()
      setEpoch((n) => n + 1)
    },
    [setApiKey, queryClient],
  )

  const isUsersMode = mode === 'users'
  const canWrite = !isUsersMode || me?.role === 'admin' || me?.role === 'operator'
  const isAdmin = isUsersMode && me?.kind === 'user' && me.role === 'admin'
  // Users mode shows nothing behind the login: no half-loaded, 401-ing console.
  const showChildren = !isUsersMode || me !== null

  return (
    <AuthCtx.Provider value={{ apiKey, setApiKey, mode, me, canWrite, isAdmin, logout }}>
      {showChildren && <Fragment key={epoch}>{children}</Fragment>}
      {locked && isUsersMode && !shareToken() && <LoginDialog onSignedIn={onSignedIn} />}
      {locked && isUsersMode && shareToken() && (
        <div role="dialog" aria-modal="true" aria-label="Share link unavailable" className="auth-gate">
          <div className="auth-gate-panel">
            <h2>Link unavailable</h2>
            <p>This share link has expired or been revoked. Ask whoever sent it for a new one.</p>
          </div>
        </div>
      )}
      {locked && !isUsersMode && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="API key required"
          className="auth-gate"
        >
          <div className="auth-gate-panel">
            <h2>API key required</h2>
            <p>The server requires an API key. It is stored for this browser session only.</p>
            <input
              type="password"
              autoFocus
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') submitKey()
              }}
              placeholder="Bearer key"
            />
            {error && <div className="auth-gate-error">{error}</div>}
            <button type="button" onClick={submitKey}>
              Unlock
            </button>
          </div>
        </div>
      )}
    </AuthCtx.Provider>
  )
}

function LoginDialog({ onSignedIn }: { onSignedIn: (token: string, me: AuthMe) => void }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!email.trim() || !password) {
      setError('Enter your email and password')
      return
    }
    setBusy(true)
    setError('')
    try {
      const res = await api.login(email.trim(), password)
      setPassword('')
      onSignedIn(res.token, {
        mode: 'users',
        kind: 'user',
        role: res.user.role,
        project_ids: res.user.role === 'admin' ? null : res.user.project_ids,
        user: res.user,
      })
    } catch (err) {
      setError(loginErrorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div role="dialog" aria-modal="true" aria-label="Sign in" className="auth-gate">
      <form className="auth-gate-panel" onSubmit={submit}>
        <h2>Sign in</h2>
        <p>Use the account your Axalon administrator created for you.</p>
        <label className="auth-gate-field">
          <span>Email</span>
          <input
            type="email"
            autoComplete="username"
            autoFocus
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <label className="auth-gate-field">
          <span>Password</span>
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        {error && (
          <div className="auth-gate-error" role="alert">
            {error}
          </div>
        )}
        <button type="submit" disabled={busy}>
          {busy ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </div>
  )
}
