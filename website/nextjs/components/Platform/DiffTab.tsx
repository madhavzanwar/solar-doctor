'use client'

import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, DiffPanel } from '@/lib/api'
import { queryKeys } from '@/lib/queryKeys'
import { useParks } from '@/components/Platform/hooks/useParks'
import { inspectionsOf, useParkSummary, type InspectionRef } from '@/components/Platform/hooks/useParkSummary'
import { SkeletonBlock, SkeletonLine, SkeletonStyle } from '@/components/Platform/Skeleton'

const NO_INSPECTIONS: InspectionRef[] = []

function labelInspection(ins: InspectionRef): string {
  const date = ins.flight_date ?? ins.created_at
  if (date) {
    const d = new Date(date)
    return isNaN(d.getTime()) ? ins.id : `${d.toLocaleDateString()} — ${ins.id.slice(0, 8)}`
  }
  return ins.id.slice(0, 16)
}

const STATUS_STYLE: Record<DiffPanel['status'], React.CSSProperties> = {
  new:       { background: '#fee2e2', color: '#991b1b' },
  resolved:  { background: '#dcfce7', color: '#166534' },
  changed:   { background: '#fed7aa', color: '#9a3412' },
  unchanged: { background: '#f1f5f9', color: '#475569' },
}

const SEVERITY_BADGE_STYLE: Record<string, React.CSSProperties> = {
  CRITICAL: { background: '#fee2e2', color: '#991b1b' },
  HIGH:     { background: '#fff7ed', color: '#9a3412' },
  MEDIUM:   { background: '#fefce8', color: '#854d0e' },
  LOW:      { background: '#f0fdf4', color: '#166534' },
}

function SeverityBadge({ severity }: { severity: string | null }) {
  if (!severity) return null
  const style = SEVERITY_BADGE_STYLE[severity] ?? { background: '#f1f5f9', color: '#475569' }
  return (
    <span style={{ ...style, fontSize: 10, fontWeight: 700, padding: '1px 6px', borderRadius: 4, textTransform: 'uppercase' }}>
      {severity}
    </span>
  )
}

export function DiffTab() {
  const { parks, loading: parksLoading } = useParks()

  const [parkId, setParkId] = useState<string>('')
  const [inspectionA, setInspectionA] = useState<string>('')
  const [inspectionB, setInspectionB] = useState<string>('')
  const [selectedPanel, setSelectedPanel] = useState<DiffPanel | null>(null)

  // Auto-select first park when parks load
  useEffect(() => {
    if (!parksLoading && parks.length > 0 && !parkId) {
      setParkId(parks[0].id)
    }
  }, [parks, parksLoading, parkId])

  // Inspection list comes from the park summary shared with History/Park Map.
  // A failed load just leaves the pickers empty.
  const summaryQuery = useParkSummary(parkId)
  const inspections = summaryQuery.isError ? NO_INSPECTIONS : inspectionsOf(summaryQuery.data)

  // Default to the two most recent inspections — once per park, so a later
  // background refetch never overrides what the user picked.
  const defaultedParkRef = useRef<string | null>(null)
  useEffect(() => {
    if (!parkId || summaryQuery.isFetching) return
    if (!summaryQuery.isSuccess && !summaryQuery.isError) return
    if (defaultedParkRef.current === parkId) return
    defaultedParkRef.current = parkId
    setSelectedPanel(null)
    if (inspections.length >= 2) {
      setInspectionA(inspections[inspections.length - 2].id)
      setInspectionB(inspections[inspections.length - 1].id)
    } else if (inspections.length === 1) {
      setInspectionA(inspections[0].id)
      setInspectionB('')
    } else {
      setInspectionA('')
      setInspectionB('')
    }
  }, [parkId, summaryQuery.isFetching, summaryQuery.isSuccess, summaryQuery.isError, inspections])

  const diffEnabled = Boolean(parkId && inspectionA && inspectionB)
  const diffQuery = useQuery({
    queryKey: queryKeys.parks.diff(parkId, inspectionA, inspectionB),
    queryFn: () => api.parkDiff(parkId, inspectionA, inspectionB),
    enabled: diffEnabled,
  })
  const loading = diffEnabled && diffQuery.isFetching
  const fetchError =
    diffEnabled && diffQuery.error && !loading
      ? diffQuery.error instanceof Error
        ? diffQuery.error.message
        : String(diffQuery.error)
      : null
  const diff = diffEnabled && !diffQuery.isError ? (diffQuery.data ?? null) : null

  // A new comparison starts with nothing selected.
  useEffect(() => {
    setSelectedPanel(null)
  }, [parkId, inspectionA, inspectionB])

  const selectRow = selectedPanel
  const totalNew = diff?.summary.new ?? 0
  const totalResolved = diff?.summary.resolved ?? 0
  const totalChanged = diff?.summary.changed ?? 0

  return (
    <div className="tab-section" style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      <SkeletonStyle />

      {/* Controls */}
      <div className="panel">
        <div className="panel-head">
          <span className="panel-title">Compare Inspections</span>
        </div>

        <div style={{ padding: '16px 20px', display: 'flex', flexWrap: 'wrap', gap: 16, alignItems: 'flex-end' }}>
          {/* Park dropdown */}
          <label style={{ display: 'flex', flexDirection: 'column', gap: 4, minWidth: 180 }}>
            <span className="eyebrow">Park</span>
            {parksLoading ? (
              <SkeletonLine height={32} />
            ) : (
              <select
                className="secondary"
                value={parkId}
                onChange={e => setParkId(e.target.value)}
                style={{ padding: '6px 10px', borderRadius: 6, border: '1px solid #e2e8f0', background: '#fff', fontSize: 14 }}
              >
                {parks.length === 0 && <option value="">No parks</option>}
                {parks.map(p => (
                  <option key={p.id} value={p.id}>{p.name ?? p.id}</option>
                ))}
              </select>
            )}
          </label>

          {/* Inspection A */}
          <label style={{ display: 'flex', flexDirection: 'column', gap: 4, minWidth: 220 }}>
            <span className="eyebrow">Inspection A (older)</span>
            <select
              className="secondary"
              value={inspectionA}
              onChange={e => setInspectionA(e.target.value)}
              style={{ padding: '6px 10px', borderRadius: 6, border: '1px solid #e2e8f0', background: '#fff', fontSize: 14 }}
            >
              {inspections.length === 0 && <option value="">—</option>}
              {inspections.map(ins => (
                <option key={ins.id} value={ins.id}>{labelInspection(ins)}</option>
              ))}
            </select>
          </label>

          {/* Inspection B */}
          <label style={{ display: 'flex', flexDirection: 'column', gap: 4, minWidth: 220 }}>
            <span className="eyebrow">Inspection B (newer)</span>
            <select
              className="secondary"
              value={inspectionB}
              onChange={e => setInspectionB(e.target.value)}
              style={{ padding: '6px 10px', borderRadius: 6, border: '1px solid #e2e8f0', background: '#fff', fontSize: 14 }}
            >
              {inspections.length === 0 && <option value="">—</option>}
              {inspections.map(ins => (
                <option key={ins.id} value={ins.id}>{labelInspection(ins)}</option>
              ))}
            </select>
          </label>
        </div>
      </div>

      {/* Summary badges */}
      {diff && !loading && (
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <span style={{ background: '#fef2f2', color: '#991b1b', padding: '6px 14px', borderRadius: 20, fontWeight: 700, fontSize: 13 }}>
            {totalNew} new fault{totalNew !== 1 ? 's' : ''}
          </span>
          <span style={{ background: '#f0fdf4', color: '#166534', padding: '6px 14px', borderRadius: 20, fontWeight: 700, fontSize: 13 }}>
            {totalResolved} resolved
          </span>
          <span style={{ background: '#fff7ed', color: '#9a3412', padding: '6px 14px', borderRadius: 20, fontWeight: 700, fontSize: 13 }}>
            {totalChanged} changed severity
          </span>
        </div>
      )}

      {/* Loading skeleton */}
      {loading && (
        <div className="panel" style={{ padding: 20, display: 'flex', flexDirection: 'column', gap: 12 }}>
          <SkeletonLine width={160} height={16} />
          <SkeletonLine width={220} height={14} />
          <SkeletonLine width={180} height={14} />
          <SkeletonBlock height={300} />
        </div>
      )}

      {/* Error */}
      {fetchError && !loading && (
        <div className="panel" style={{ padding: 20 }}>
          <p style={{ color: '#991b1b', margin: 0 }}>{fetchError}</p>
        </div>
      )}

      {/* Empty prompt */}
      {!loading && !diff && !fetchError && (!inspectionA || !inspectionB) && (
        <div className="panel empty" style={{ padding: 40, textAlign: 'center' }}>
          <p className="muted">Select two inspections above to compare.</p>
        </div>
      )}

      {/* Panel grid */}
      {!loading && diff && diff.panels.length > 0 && (
        <div className="panel">
          <div className="panel-head">
            <span className="panel-title">Panel Map</span>
            <span className="muted" style={{ fontSize: 12 }}>{diff.panels.length} panels</span>
          </div>

          <div style={{ padding: '16px 20px' }}>
            {/* Legend */}
            <div style={{ display: 'flex', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
              {(['new', 'resolved', 'changed', 'unchanged'] as DiffPanel['status'][]).map(s => (
                <span key={s} style={{ ...STATUS_STYLE[s], padding: '2px 10px', borderRadius: 4, fontSize: 11, fontWeight: 600, textTransform: 'capitalize' }}>
                  {s}
                </span>
              ))}
            </div>

            {/* Grid */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(48px, 1fr))',
                gap: 4,
              }}
            >
              {diff.panels.map(panel => {
                const isSelected = selectedPanel?.panel_id === panel.panel_id
                return (
                  <button
                    key={panel.panel_id}
                    onClick={() => setSelectedPanel(isSelected ? null : panel)}
                    title={`${panel.panel_id} — ${panel.status}`}
                    style={{
                      ...STATUS_STYLE[panel.status],
                      width: 40,
                      height: 40,
                      border: isSelected ? '2px solid #0f172a' : '1px solid rgba(0,0,0,0.08)',
                      borderRadius: 4,
                      fontSize: 9,
                      fontWeight: 600,
                      cursor: 'pointer',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                      padding: '0 2px',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    {panel.panel_id.split('-').pop() ?? panel.panel_id}
                  </button>
                )
              })}
            </div>
          </div>

          {/* Inline side panel */}
          {selectedPanel && (
            <div style={{ borderTop: '1px solid #e2e8f0', padding: '16px 20px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                <span style={{ fontWeight: 700, fontSize: 15 }}>
                  Panel {selectedPanel.panel_id}
                  <span style={{ ...STATUS_STYLE[selectedPanel.status], marginLeft: 10, padding: '2px 8px', borderRadius: 4, fontSize: 11, fontWeight: 600, textTransform: 'capitalize' }}>
                    {selectedPanel.status}
                  </span>
                </span>
                <button
                  onClick={() => setSelectedPanel(null)}
                  aria-label="Close panel"
                  style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 18, color: '#64748b', lineHeight: 1 }}
                >
                  ×
                </button>
              </div>

              <div className="diff-columns" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
                {/* Inspection A column */}
                <div>
                  <p className="eyebrow diff-column-label" style={{ marginBottom: 10 }}>Inspection A</p>
                  {selectedPanel.detections_a.length === 0 ? (
                    <p className="muted" style={{ fontSize: 13 }}>No faults in this inspection.</p>
                  ) : (
                    <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 6 }}>
                      {selectedPanel.detections_a.map((d, i) => (
                        <li key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
                          <span style={{ flex: 1 }}>{d.class}</span>
                          <SeverityBadge severity={d.severity} />
                          {d.confidence != null && (
                            <span className="muted" style={{ fontSize: 11 }}>{(d.confidence * 100).toFixed(0)}%</span>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>

                {/* Inspection B column */}
                <div>
                  <p className="eyebrow diff-column-label" style={{ marginBottom: 10 }}>Inspection B</p>
                  {selectedPanel.detections_b.length === 0 ? (
                    <p className="muted" style={{ fontSize: 13 }}>No faults in this inspection.</p>
                  ) : (
                    <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 6 }}>
                      {selectedPanel.detections_b.map((d, i) => (
                        <li key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
                          <span style={{ flex: 1 }}>{d.class}</span>
                          <SeverityBadge severity={d.severity} />
                          {d.confidence != null && (
                            <span className="muted" style={{ fontSize: 11 }}>{(d.confidence * 100).toFixed(0)}%</span>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* No panels returned */}
      {!loading && diff && diff.panels.length === 0 && (
        <div className="panel empty" style={{ padding: 40, textAlign: 'center' }}>
          <p className="muted">No panels found for this comparison.</p>
        </div>
      )}
    </div>
  )
}
