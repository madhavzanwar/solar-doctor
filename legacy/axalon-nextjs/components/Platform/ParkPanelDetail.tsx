'use client'

import type { GridPanel, GridPanelDetection } from '@/lib/api'
import { API_BASE, api } from '@/lib/api'
import { ThermalReadout } from '@/components/Platform/ThermalReadout'

const SEVERITY_COLOR: Record<string, string> = {
  CRITICAL: '#dc2626',
  HIGH: '#ea580c',
  MEDIUM: '#ca8a04',
  LOW: '#2563eb',
}

export function ParkPanelDetail({
  panel,
  jobId,
  onClose,
}: {
  panel: GridPanel | null
  jobId: string | null
  onClose: () => void
}) {
  if (!panel) {
    return (
      <aside
        aria-label="Panel detail"
        style={{
          padding: 20,
          background: '#ffffff',
          border: '1px solid #e2e8f0',
          borderRadius: 8,
          minHeight: 280,
          color: '#64748b',
          fontSize: 13,
        }}
      >
        Click a panel in the grid to see its detections.
      </aside>
    )
  }

  const firstFile = panel.detections.find((d) => d.thermal_filename)?.thermal_filename
  const keyParam = api.authQuery('?')
  const thumbUrl =
    jobId && firstFile
      ? `${API_BASE}/results/${encodeURIComponent(jobId)}/${encodeURIComponent(firstFile)}${keyParam}`
      : null

  return (
    <aside
      aria-label={`Panel ${panel.panel_id} detail`}
      style={{
        padding: 20,
        background: '#ffffff',
        border: '1px solid #e2e8f0',
        borderRadius: 8,
        display: 'flex',
        flexDirection: 'column',
        gap: 14,
      }}
    >
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700 }}>Panel {panel.panel_id}</h3>
        <button
          onClick={onClose}
          aria-label="Close panel detail"
          style={{
            background: 'transparent',
            border: 'none',
            cursor: 'pointer',
            color: '#94a3b8',
            fontSize: 18,
            lineHeight: 1,
          }}
        >
          ×
        </button>
      </header>

      <div style={{ fontSize: 13, color: '#475569' }}>
        {panel.detection_count} detection{panel.detection_count === 1 ? '' : 's'}
        {panel.worst_severity ? (
          <span
            style={{
              marginLeft: 8,
              padding: '2px 8px',
              background: SEVERITY_COLOR[panel.worst_severity],
              color: '#fff',
              borderRadius: 4,
              fontSize: 11,
              fontWeight: 700,
            }}
          >
            {panel.worst_severity}
          </span>
        ) : null}
      </div>

      <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: 6 }}>
        {panel.detections.map((d, i) => (
          <DetectionRow key={i} d={d} />
        ))}
      </ul>

      {thumbUrl ? (
        <figure style={{ margin: 0 }}>
          <img
            src={thumbUrl}
            alt={`Thermal image ${firstFile}`}
            style={{ width: '100%', maxHeight: 240, objectFit: 'contain', borderRadius: 4, background: '#0f172a' }}
          />
          <figcaption style={{ fontSize: 11, color: '#94a3b8', marginTop: 4 }}>{firstFile}</figcaption>
        </figure>
      ) : null}

      {panel.gps ? (
        <div style={{ fontSize: 12, color: '#64748b' }}>
          GPS: {panel.gps.lat.toFixed(5)}, {panel.gps.lon.toFixed(5)}
        </div>
      ) : null}
    </aside>
  )
}

function DetectionRow({ d }: { d: GridPanelDetection }) {
  return (
    <li
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        gap: 8,
        padding: '6px 10px',
        background: '#f8fafc',
        borderRadius: 4,
        fontSize: 12,
      }}
    >
      <span style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        <span style={{ fontWeight: 600 }}>{d.class}</span>
        <ThermalReadout max_temp={d.max_temp} delta_t_measured={d.delta_t_measured} />
      </span>
      <span style={{ color: '#64748b' }}>
        {d.confidence != null ? `${Math.round(d.confidence * 100)}%` : ''}
        {d.severity ? (
          <span
            style={{
              marginLeft: 8,
              padding: '1px 6px',
              background: SEVERITY_COLOR[d.severity] ?? '#64748b',
              color: '#fff',
              borderRadius: 3,
              fontSize: 10,
              fontWeight: 700,
            }}
          >
            {d.severity}
          </span>
        ) : null}
      </span>
    </li>
  )
}
