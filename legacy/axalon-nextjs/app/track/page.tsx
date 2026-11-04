'use client'

import { ToastProvider } from '@/components/Platform/Toast'
import { TrackGate } from '@/components/Track/TrackGate'
import { InventoryTab } from '@/components/Platform/InventoryTab'
import { TrackNotesPanel } from '@/components/Track/TrackNotesPanel'
import { TrackFilesPanel } from '@/components/Track/TrackFilesPanel'

export default function TrackPage() {
  return (
    <ToastProvider>
      <TrackGate>
        <main className="ax-page track-page">
          <div className="track-scroll">
            <InventoryTab />
            <div className="track-side-grid">
              <TrackNotesPanel />
              <TrackFilesPanel />
            </div>
          </div>
        </main>
      </TrackGate>
    </ToastProvider>
  )
}
