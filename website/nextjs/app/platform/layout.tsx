import type { Metadata } from 'next'
import { AuthGate } from '@/components/Platform/AuthGate'
import { QueryProvider } from '@/components/Providers/QueryProvider'
import './platform.css'

export const metadata: Metadata = {
  title: 'Axalon · Internal Inspection Console',
  description: 'Internal batch inspection console — restricted access.',
  robots: { index: false, follow: false },
}

export default function PlatformLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <div className="console-root">
      <header className="console-topbar">
        <div className="console-topbar-left">
          <span className="console-badge">Internal</span>
          <span className="console-title">
            Axalon <em>Inspection Console</em>
          </span>
        </div>
        <div className="console-topbar-right">
          <span className="console-meta">BUILD 1.0.0</span>
          <span className="console-meta online">
            <i aria-hidden="true" /> ONLINE
          </span>
        </div>
        <div className="thermal-strip" aria-hidden="true" />
      </header>

      <div className="console-body">
        <QueryProvider>
          <AuthGate>{children}</AuthGate>
        </QueryProvider>
      </div>
    </div>
  )
}
