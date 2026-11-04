import type { Metadata } from 'next'
import DynamicCursor from '@/components/DynamicCursor'

export const metadata: Metadata = {
  title: 'Axalon Systems — Autonomous Solar Inspection',
  description:
    'AI-powered drone inspection for solar assets. Thermal + RGB computer vision with YOLO11m for 11-class fault detection.',
}

export default function SiteLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <>
      <DynamicCursor />
      <main>{children}</main>
    </>
  )
}
