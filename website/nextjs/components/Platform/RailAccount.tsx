'use client'

import { LogOut } from 'lucide-react'
import { useAuth } from '@/components/Platform/AuthGate'

/** Rail footer identity block. Renders nothing unless the API runs users mode. */
export function RailAccount() {
  const { mode, me, logout } = useAuth()
  if (mode !== 'users' || !me) return null

  if (me.kind === 'share') {
    return (
      <div className="rail-account" data-testid="rail-account">
        <div className="rail-account-name">Shared view</div>
        <div className="rail-account-role">read-only</div>
      </div>
    )
  }

  return (
    <div className="rail-account" data-testid="rail-account">
      <div className="rail-account-name" title={me.user?.email ?? ''}>
        {me.user?.email}
      </div>
      <div className="rail-account-row">
        <span className={`rail-account-role role-${me.role}`}>{me.role}</span>
        <button type="button" className="rail-account-logout" onClick={() => void logout()} aria-label="Sign out">
          <LogOut size={12} />
          <span>Sign out</span>
        </button>
      </div>
    </div>
  )
}
