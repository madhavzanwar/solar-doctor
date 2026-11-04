import type { Metadata } from 'next'
import { AuthGate } from '@/components/Platform/AuthGate'
import { QueryProvider } from '@/components/Providers/QueryProvider'
import '../platform/platform.css'
import './track.css'

export const metadata: Metadata = {
  title: 'Axalon · Track',
  description: 'Internal hardware tracking workspace — restricted access.',
  robots: { index: false, follow: false },
}

export default function TrackLayout({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: '#f4f5f7',
        color: '#111827',
        fontFamily:
          'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
        overflow: 'hidden',
      }}
    >
      <header
        style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          height: 48,
          padding: '0 18px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          background: '#ffffff',
          borderBottom: '1px solid #d6dbe3',
          zIndex: 100,
          fontSize: 12,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <span
            style={{
              padding: '4px 8px',
              borderRadius: 4,
              background: '#111827',
              color: '#ffffff',
              border: '1px solid #111827',
              fontWeight: 700,
            }}
          >
            INTERNAL
          </span>
          <span style={{ fontWeight: 700, fontSize: 14, color: '#111827' }}>
            Axalon Track — Hardware & Research
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, color: '#475569' }}>
          <a href="/platform" style={{ color: '#0ea5e9', textDecoration: 'none' }}>
            Inspection console →
          </a>
        </div>
      </header>

      <div style={{ paddingTop: 48, height: '100%' }}>
        {/* InventoryTab and the Track panels read through react-query. */}
        <QueryProvider>
          <AuthGate>{children}</AuthGate>
        </QueryProvider>
      </div>
    </div>
  )
}
