'use client'

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'

type ToastKind = 'error' | 'info' | 'success'
type Toast = { id: number; kind: ToastKind; text: string }

type ToastCtx = {
  push: (kind: ToastKind, text: string) => void
  error: (text: string) => void
  info: (text: string) => void
  success: (text: string) => void
}

const Ctx = createContext<ToastCtx | null>(null)

// Per-kind visibility durations (ms): errors linger, success is brief.
const TOAST_DURATION: Record<ToastKind, number> = {
  error: 6000,
  info: 4000,
  success: 3000,
}

export function useToast(): ToastCtx {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useToast must be used inside <ToastProvider>')
  return ctx
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const push = useCallback((kind: ToastKind, text: string) => {
    const id = Date.now() + Math.random()
    setToasts((t) => [...t, { id, kind, text }])
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), TOAST_DURATION[kind])
  }, [])

  const api: ToastCtx = {
    push,
    error: (t) => push('error', t),
    info: (t) => push('info', t),
    success: (t) => push('success', t),
  }

  return (
    <Ctx.Provider value={api}>
      {children}
      <div
        style={{
          position: 'fixed',
          right: 16,
          bottom: 16,
          display: 'flex',
          flexDirection: 'column',
          gap: 8,
          zIndex: 9999,
          maxWidth: 480,
        }}
      >
        {toasts.map((t) => (
          <div
            key={t.id}
            role={t.kind === 'error' ? 'alert' : 'status'}
            style={{
              background:
                t.kind === 'error' ? '#7f1d1d' : t.kind === 'success' ? '#14532d' : '#1e293b',
              color: '#fff',
              padding: '10px 14px',
              borderRadius: 8,
              border: t.kind === 'error' ? '1px solid #f87171' : '1px solid transparent',
              fontSize: 13,
              lineHeight: 1.4,
              boxShadow: '0 8px 24px rgba(0,0,0,0.25)',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
            }}
          >
            {t.text}
          </div>
        ))}
      </div>
    </Ctx.Provider>
  )
}
