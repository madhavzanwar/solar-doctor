'use client'

import type { GridPanel, ParkGrid, Severity } from '@/lib/api'

const SEVERITY_COLOR: Record<Severity, string> = {
  CRITICAL: '#dc2626',
  HIGH: '#ea580c',
  MEDIUM: '#ca8a04',
  LOW: '#2563eb',
}
const EMPTY_COLOR = '#e2e8f0'
const SELECTED_RING = '#0ea5e9'

export function ParkMapGrid({
  grid,
  selectedPanelId,
  onSelect,
}: {
  grid: ParkGrid | null
  selectedPanelId: string | null
  onSelect: (panel: GridPanel) => void
}) {
  if (!grid) {
    return <div style={{ padding: 16, color: '#64748b', fontSize: 13 }}>Loading grid…</div>
  }
  if (grid.panels.length === 0) {
    return (
      <div style={{ padding: 24, color: '#64748b', fontSize: 13, textAlign: 'center' }}>
        No panel detections yet for this inspection.
      </div>
    )
  }

  const byKey = new Map<string, GridPanel>()
  for (const p of grid.panels) byKey.set(`${p.row}|${p.col}`, p)
  const rows = Math.max(grid.rows, ...grid.panels.map((p) => p.row + 1), 1)
  const cols = Math.max(grid.cols, ...grid.panels.map((p) => p.col + 1), 1)

  return (
    <div>
      <Legend />
      <div
        role="grid"
        aria-label={`Park ${grid.park_id} panel grid`}
        style={{
          display: 'grid',
          gridTemplateColumns: `repeat(${cols}, minmax(20px, 1fr))`,
          gap: 4,
          padding: 12,
          background: '#f8fafc',
          borderRadius: 8,
          border: '1px solid #e2e8f0',
        }}
      >
        {Array.from({ length: rows * cols }).map((_, i) => {
          const r = Math.floor(i / cols)
          const c = i % cols
          const panel = byKey.get(`${r}|${c}`)
          const fill = panel?.worst_severity ? SEVERITY_COLOR[panel.worst_severity] : EMPTY_COLOR
          const isSelected = panel?.panel_id === selectedPanelId
          return (
            <button
              key={i}
              role="gridcell"
              data-testid={panel ? `panel-${panel.panel_id}` : `panel-empty-${r}-${c}`}
              aria-label={
                panel
                  ? `Panel ${panel.panel_id}, ${panel.detection_count} detections, worst ${panel.worst_severity ?? 'none'}`
                  : `Empty panel R${r + 1}-C${c + 1}`
              }
              onClick={panel ? () => onSelect(panel) : undefined}
              disabled={!panel}
              style={{
                aspectRatio: '1 / 1',
                background: fill,
                border: isSelected ? `2px solid ${SELECTED_RING}` : '1px solid rgba(0,0,0,0.08)',
                borderRadius: 3,
                cursor: panel ? 'pointer' : 'default',
                padding: 0,
                fontSize: 0,
              }}
            />
          )
        })}
      </div>
    </div>
  )
}

function Legend() {
  const entries: Array<[string, string]> = [
    ['CRITICAL', SEVERITY_COLOR.CRITICAL],
    ['HIGH', SEVERITY_COLOR.HIGH],
    ['MEDIUM', SEVERITY_COLOR.MEDIUM],
    ['LOW', SEVERITY_COLOR.LOW],
    ['Clean', EMPTY_COLOR],
  ]
  return (
    <div style={{ display: 'flex', gap: 12, alignItems: 'center', padding: '8px 12px', fontSize: 12, color: '#475569' }}>
      {entries.map(([label, color]) => (
        <span key={label} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <span style={{ width: 12, height: 12, background: color, borderRadius: 2, border: '1px solid rgba(0,0,0,0.1)' }} />
          {label}
        </span>
      ))}
    </div>
  )
}
