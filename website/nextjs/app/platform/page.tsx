'use client'

import { useState } from 'react'
import type { PlannedPoint } from '@/lib/missionToWaypoints'
import dynamic from 'next/dynamic'
import {
  LayoutDashboard,
  BarChart3,
  Image as ImageIcon,
  History as HistoryIcon,
  SlidersHorizontal,
  MapIcon,
  GitCompare,
  Navigation2,
  Radio,
  FolderKanban,
} from 'lucide-react'
import { ToastProvider } from '@/components/Platform/Toast'
import { OperationsTab } from '@/components/Platform/OperationsTab'
import { InspectTab } from '@/components/Platform/InspectTab'
import { HistoryTab } from '@/components/Platform/HistoryTab'
import { ParkMapTab } from '@/components/Platform/ParkMapTab'
import { SettingsTab } from '@/components/Platform/SettingsTab'
import { DiffTab } from '@/components/Platform/DiffTab'
import { PlanTab } from '@/components/Platform/PlanTab'
import { OverviewTab } from '@/components/Platform/OverviewTab'
import { AssetsTab } from '@/components/Platform/AssetsTab'
import { useAuth } from '@/components/Platform/AuthGate'
import { RailAccount } from '@/components/Platform/RailAccount'

const LiveOpsTab = dynamic(() => import('@/components/Platform/LiveOpsTab'), { ssr: false })

type Tab =
  | 'operations'
  | 'inspect'
  | 'history'
  | 'settings'
  | 'parkmap'
  | 'diff'
  | 'plan'
  | 'overview'
  | 'liveops'
  | 'assets'

export default function PlatformPage() {
  return (
    <ToastProvider>
      <PlatformShell />
    </ToastProvider>
  )
}

function PlatformShell() {
  const [tab, setTab] = useState<Tab>('operations')
  // Lives here, not in PlanTab: tabs unmount on switch, so the route must
  // outlive PlanTab to still be there when the operator opens Live Ops.
  const [plannedRoute, setPlannedRoute] = useState<PlannedPoint[]>([])
  // Inspect and Live Ops exist only to create data or fly the drone — viewers and
  // share-link visitors never see them (the API refuses them regardless).
  const { canWrite } = useAuth()

  return (
    <main className="ax-page">
      <div className="shell">
        {/* Rail navigation */}
        <aside className="rail">
          {/* Rail brand */}
          <div className="rail-brand">
            <div className="rail-mark" aria-hidden="true">
              AX
            </div>
            <div className="rail-brand-text">
              <strong>Axalon</strong>
              <span>Thermal Ops</span>
            </div>
          </div>
          <div className="rail-spectrum" aria-hidden="true" />

          {/* Navigation buttons */}
          <nav className="rail-nav tab-bar">
            <div className="rail-group">Monitor</div>
            <button
              type="button"
              className={`rail-link ${tab === 'overview' ? 'active' : ''}`}
              onClick={() => setTab('overview')}
              title="Overview"
              aria-label="Overview"
            >
              <BarChart3 size={16} />
              <span>Overview</span>
            </button>
            <button
              type="button"
              className={`rail-link ${tab === 'operations' ? 'active' : ''}`}
              onClick={() => setTab('operations')}
              title="Operations"
              aria-label="Operations"
            >
              <LayoutDashboard size={16} />
              <span>Operations</span>
            </button>
            {canWrite && (
              <button
                type="button"
                className={`rail-link ${tab === 'inspect' ? 'active' : ''}`}
                onClick={() => setTab('inspect')}
                title="Inspect"
                aria-label="Inspect"
              >
                <ImageIcon size={16} />
                <span>Inspect</span>
              </button>
            )}
            <button
              type="button"
              className={`rail-link ${tab === 'history' ? 'active' : ''}`}
              onClick={() => setTab('history')}
              title="History"
              aria-label="History"
            >
              <HistoryIcon size={16} />
              <span>History</span>
            </button>
            <div className="rail-group">Field</div>
            <button
              type="button"
              className={`rail-link ${tab === 'parkmap' ? 'active' : ''}`}
              onClick={() => setTab('parkmap')}
              title="Park Map"
              aria-label="Park Map"
              data-testid="tab-parkmap"
            >
              <MapIcon size={16} />
              <span>Park Map</span>
            </button>
            <button
              type="button"
              className={`rail-link ${tab === 'diff' ? 'active' : ''}`}
              onClick={() => setTab('diff')}
              title="Diff"
              aria-label="Diff"
            >
              <GitCompare size={16} />
              <span>Diff</span>
            </button>
            <button
              type="button"
              className={`rail-link ${tab === 'plan' ? 'active' : ''}`}
              onClick={() => setTab('plan')}
              title="Plan"
              aria-label="Plan"
              data-testid="tab-plan"
            >
              <Navigation2 size={16} />
              <span>Plan</span>
            </button>
            {canWrite && (
              <button
                type="button"
                className={`rail-link ${tab === 'liveops' ? 'active' : ''}`}
                onClick={() => setTab('liveops')}
                title="Live Ops"
                aria-label="Live Ops"
                data-testid="tab-liveops"
              >
                <Radio size={16} />
                <span>Live Ops</span>
              </button>
            )}
            <div className="rail-group">Manage</div>
            <button
              type="button"
              className={`rail-link ${tab === 'assets' ? 'active' : ''}`}
              onClick={() => setTab('assets')}
              title="Assets"
              aria-label="Assets"
              data-testid="tab-assets"
            >
              <FolderKanban size={16} />
              <span>Assets</span>
            </button>
            <button
              type="button"
              className={`rail-link ${tab === 'settings' ? 'active' : ''}`}
              onClick={() => setTab('settings')}
              title="Settings"
              aria-label="Settings"
            >
              <SlidersHorizontal size={16} />
              <span>Settings</span>
            </button>
          </nav>

          {/* Rail footer */}
          <div className="rail-foot">
            <div className="rail-status ok">
              <span />
              Detector online
            </div>
            <div className="rail-foot-line">YOLO11 · 11 fault classes</div>
            <RailAccount />
          </div>
        </aside>

        {/* Main content area */}
        <div className="wrap tab-content platform-container">
          {tab === 'overview' && <OverviewTab onTabChange={setTab} />}
          {tab === 'operations' && <OperationsTab />}
          {tab === 'inspect' && canWrite && <InspectTab />}
          {tab === 'history' && <HistoryTab />}
          {tab === 'settings' && <SettingsTab />}
          {tab === 'parkmap' && <ParkMapTab />}
          {tab === 'diff' && <DiffTab />}
          {tab === 'plan' && <PlanTab onRouteChange={setPlannedRoute} />}
          {tab === 'liveops' && canWrite && <LiveOpsTab droneId="drone-01" plannedPoints={plannedRoute} />}
          {tab === 'assets' && <AssetsTab />}
        </div>
      </div>
    </main>
  )
}
