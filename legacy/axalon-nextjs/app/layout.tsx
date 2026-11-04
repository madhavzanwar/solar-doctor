import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Axalon Systems',
  description:
    'AI-powered drone inspection for solar assets. Thermal + RGB computer vision with YOLO11m for 11-class fault detection.',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}
