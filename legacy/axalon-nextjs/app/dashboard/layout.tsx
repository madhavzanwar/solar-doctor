import type { Metadata } from 'next'
import './dashboard.css'

export const metadata: Metadata = {
  title: 'Axalon · AXA-9 Mission Report',
  description: 'AXA-9 autonomous thermal inspection mission report — Block 04.',
  robots: { index: false, follow: false },
}

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <div
      className="axa-dashboard"
      style={{
        position: 'fixed',
        inset: 0,
        background: '#08080f',
        color: '#e8e8f0',
        fontFamily: 'Space Grotesk, sans-serif',
        overflow: 'hidden',
      }}
    >
      {children}
    </div>
  )
}
