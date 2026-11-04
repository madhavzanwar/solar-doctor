import type { Metadata } from 'next'
import './agents.css'

export const metadata: Metadata = {
  title: 'Axalon · Agent Console',
  description: 'Autonomous coding agent control panel.',
  robots: { index: false, follow: false },
}

export default function AgentsLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="ac-shell">
      <header className="ac-header">
        <div className="ac-header-left">
          <span className="ac-badge">INTERNAL</span>
          <span className="ac-title">Axalon Agent Console</span>
        </div>
        <div className="ac-header-right">
          <span className="ac-version">BUILD 1.0.0</span>
          <span className="ac-dot" />
          <span className="ac-online">ONLINE</span>
        </div>
      </header>
      <div className="ac-body">{children}</div>
    </div>
  )
}
