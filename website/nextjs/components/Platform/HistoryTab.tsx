'use client'

import { History as HistoryIcon } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useParks } from '@/components/Platform/hooks/useParks'
import { useParkSummary } from '@/components/Platform/hooks/useParkSummary'
import { useErrorToast } from '@/components/Platform/hooks/useErrorToast'
import { queryKeys } from '@/lib/queryKeys'
import { TrendChart } from '@/components/Platform/TrendChart'
import { ErrorBanner } from '@/components/Platform/ErrorBanner'
import { SkeletonLine } from '@/components/Platform/Skeleton'
import { api, ApiError, type RecurringPanel, type RevenueLoss, type TrendPoint } from '@/lib/api'
import { formatRevenueLoss, REVENUE_LOSS_NOTE } from '@/lib/thermalFormat'

type SortColumn = 'date' | 'images' | 'detections' | 'critical' | 'high' | 'loss'
type SortDirection = 'asc' | 'desc'

const NO_TREND: TrendPoint[] = []
const NO_RECURRING: RecurringPanel[] = []

function errorMessage(err: unknown): string {
  return err instanceof ApiError ? err.message : String(err)
}

function sevCountOf(summary: Record<string, number> | undefined, key: string): number {
  const s = summary || {}
  return Number(s[key] ?? s[key.toUpperCase()] ?? s[key.toLowerCase()] ?? 0)
}

type InspectionRow = RevenueLoss & {
  id: number
  flight_date?: string
  total_images?: number
  total_detections?: number
  summary?: Record<string, number>
}

type ParkSummary = {
  park_id: string
  name?: string
  mode?: string
  total_panels?: number
  total_inspections?: number
  inspections?: InspectionRow[]
}

function Chip({
  label,
  value,
  tone,
}: {
  label: string
  value: string
  tone: 'info' | 'ok' | 'crit' | 'muted'
}) {
  return (
    <div className={`chip chip-${tone}`}>
      <span className="chip-label">{label}</span>
      <span className="chip-value">{value}</span>
    </div>
  )
}

function HistoryChart({ inspections }: { inspections: InspectionRow[] }) {
  if (!inspections.length) return null
  const points = [...inspections].reverse() // chronological
  const w = 720
  const h = 160
  const pad = 24
  const totalOf = (p: InspectionRow) => p.total_detections ?? 0
  const critOf = (p: InspectionRow) =>
    Number(p.summary?.CRITICAL ?? p.summary?.critical ?? 0)
  const max = Math.max(1, ...points.map(totalOf))
  const stepX = points.length > 1 ? (w - pad * 2) / (points.length - 1) : 0
  const px = (i: number) => pad + i * stepX
  const py = (v: number) => h - pad - ((v || 0) / max) * (h - pad * 2)
  const linePath = points
    .map((p, i) => `${i === 0 ? 'M' : 'L'} ${px(i).toFixed(1)} ${py(totalOf(p)).toFixed(1)}`)
    .join(' ')
  const critPath = points
    .map((p, i) => `${i === 0 ? 'M' : 'L'} ${px(i).toFixed(1)} ${py(critOf(p)).toFixed(1)}`)
    .join(' ')

  return (
    <div className="chart-card">
      <div className="chart-head">
        <strong>Detections over time</strong>
        <span className="muted">
          <span className="dot" style={{ background: '#111827' }} /> total ·
          <span className="dot" style={{ background: '#dc2626', marginLeft: 8 }} /> critical
        </span>
      </div>
      <svg
        width="100%"
        viewBox={`0 0 ${w} ${h}`}
        preserveAspectRatio="none"
        className="chart-svg history-chart-svg"
      >
        <line x1={pad} y1={h - pad} x2={w - pad} y2={h - pad} stroke="#e2e8f0" />
        <line x1={pad} y1={pad} x2={pad} y2={h - pad} stroke="#e2e8f0" />
        <path d={linePath} fill="none" stroke="#111827" strokeWidth={2} />
        <path d={critPath} fill="none" stroke="#dc2626" strokeWidth={2} strokeDasharray="4 3" />
        {points.map((p, i) => (
          <circle key={i} cx={px(i)} cy={py(totalOf(p))} r={3} fill="#111827" />
        ))}
        <text x={pad} y={pad - 6} fontSize="10" fill="#64748b">
          {max}
        </text>
        <text x={pad} y={h - pad + 14} fontSize="10" fill="#64748b">
          0
        </text>
      </svg>
    </div>
  )
}

export function HistoryTab() {
  const { parks } = useParks()

  const [historyParkId, setHistoryParkId] = useState<string>('')
  const [sort, setSort] = useState<{ column: SortColumn; direction: SortDirection }>({
    column: 'date',
    direction: 'desc',
  })

  // Default to first park once loaded
  useEffect(() => {
    if (!historyParkId && parks[0]) {
      setHistoryParkId(parks[0].id)
    }
  }, [parks, historyParkId])

  const summaryQuery = useParkSummary(historyParkId)
  useErrorToast(summaryQuery.error, errorMessage)
  // Skeleton only while there is nothing to show; a retry after an error also
  // counts, so the banner gives way to the skeleton as it did before.
  const historyLoading = summaryQuery.isFetching && !summaryQuery.data
  const historyError = summaryQuery.error ? errorMessage(summaryQuery.error) : null
  const parkSummary = summaryQuery.isError ? null : ((summaryQuery.data as ParkSummary | undefined) ?? null)

  const trendQuery = useQuery({
    queryKey: queryKeys.parks.trend(historyParkId),
    queryFn: () => api.parkTrend(historyParkId),
    enabled: Boolean(historyParkId),
  })
  useErrorToast(trendQuery.error, errorMessage)
  const trendData = trendQuery.data ?? NO_TREND
  const trendLoading = trendQuery.isFetching && !trendQuery.data

  // Recurring faults are optional context: a failure just hides the section.
  const recurringQuery = useQuery({
    queryKey: queryKeys.parks.recurring(historyParkId),
    queryFn: () => api.parkRecurring(historyParkId),
    enabled: Boolean(historyParkId),
  })
  const recurringData = recurringQuery.data ?? NO_RECURRING

  const inspections = parkSummary?.inspections ?? []
  const sortedInspections = useMemo(() => {
    const valueOf = (ins: InspectionRow): number => {
      switch (sort.column) {
        case 'date':
          return ins.flight_date ? new Date(ins.flight_date).getTime() : 0
        case 'images':
          return ins.total_images ?? 0
        case 'detections':
          return ins.total_detections ?? 0
        case 'critical':
          return sevCountOf(ins.summary, 'CRITICAL')
        case 'high':
          return sevCountOf(ins.summary, 'HIGH')
        case 'loss':
          return ins.revenue_loss_usd ?? 0
      }
    }
    const factor = sort.direction === 'asc' ? 1 : -1
    return [...inspections].sort((a, b) => (valueOf(a) - valueOf(b)) * factor)
  }, [inspections, sort])

  const toggleSort = (column: SortColumn) =>
    setSort((prev) =>
      prev.column === column
        ? { column, direction: prev.direction === 'asc' ? 'desc' : 'asc' }
        : { column, direction: 'desc' },
    )

  const sortArrow = (column: SortColumn) =>
    sort.column === column ? (
      <span className="hist-sort-arrow">{sort.direction === 'asc' ? '▲' : '▼'}</span>
    ) : null

  return (
    <section className="tab-section">
      <header className="cmdbar">
        <div className="cmdbar-titles">
          <div className="eyebrow">
            <HistoryIcon size={13} />
            Inspection history
          </div>
          <h1>History</h1>
        </div>
        <div className="chips">
          <Chip label="Parks" value={String(parks.length)} tone="muted" />
          <Chip
            label="Flights"
            value={String(parkSummary?.total_inspections ?? 0)}
            tone="info"
          />
          <Chip
            label="Latest"
            value={
              parkSummary?.inspections?.[0]?.flight_date
                ? new Date(parkSummary.inspections[0].flight_date!).toLocaleDateString()
                : '—'
            }
            tone="ok"
          />
        </div>
      </header>

      <section className="panel">
        <div className="panel-head">
          <div>
            <div className="panel-title">Select park</div>
            <p>Pick a park to load its inspection history.</p>
          </div>
          <select
            value={historyParkId}
            onChange={(e) => setHistoryParkId(e.target.value)}
            style={{ minWidth: 220 }}
          >
            {parks.length === 0 && <option value="">No parks</option>}
            {parks.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name ? `${p.id} — ${p.name}` : p.id}
              </option>
            ))}
          </select>
        </div>

        {historyError && !historyLoading && (
          <ErrorBanner message={historyError} onRetry={() => void summaryQuery.refetch()} />
        )}
        {historyLoading && (
          <div className="table" style={{ marginTop: 16 }}>
            <div className="table-head hist-head">
              <span>Date</span>
              <span>Images</span>
              <span>Detections</span>
              <span>Critical</span>
              <span>High</span>
            </div>
            {[0, 1, 2, 3, 4].map((i) => (
              <div className="hist-row" key={i}>
                <SkeletonLine />
                <SkeletonLine width={40} />
                <SkeletonLine width={40} />
                <SkeletonLine width={32} />
                <SkeletonLine width={32} />
              </div>
            ))}
          </div>
        )}
        {!historyLoading && !historyError && parkSummary && parkSummary.inspections && (
          <>
            <HistoryChart inspections={parkSummary.inspections} />
            <div className="table" style={{ marginTop: 16 }}>
              <div className="table-head hist-head with-loss sortable">
                <span onClick={() => toggleSort('date')}>Date {sortArrow('date')}</span>
                <span onClick={() => toggleSort('images')}>Images {sortArrow('images')}</span>
                <span onClick={() => toggleSort('detections')}>Detections {sortArrow('detections')}</span>
                <span onClick={() => toggleSort('critical')}>Critical {sortArrow('critical')}</span>
                <span onClick={() => toggleSort('high')}>High {sortArrow('high')}</span>
                <span onClick={() => toggleSort('loss')} title={REVENUE_LOSS_NOTE}>
                  Est. loss/day {sortArrow('loss')}
                </span>
              </div>
              {sortedInspections.map((ins) => (
                <div className="hist-row with-loss" key={ins.id}>
                  <span>
                    {ins.flight_date
                      ? new Date(ins.flight_date).toLocaleString()
                      : `#${ins.id}`}
                  </span>
                  <span>{ins.total_images ?? '—'}</span>
                  <span>{ins.total_detections ?? 0}</span>
                  <span>
                    <strong style={{ color: '#991b1b' }}>{sevCountOf(ins.summary, 'CRITICAL')}</strong>
                  </span>
                  <span style={{ color: '#cc5500' }}>{sevCountOf(ins.summary, 'HIGH')}</span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums' }}>
                    {formatRevenueLoss(ins.revenue_loss_usd, ins.revenue_currency) ?? '—'}
                  </span>
                </div>
              ))}
              {sortedInspections.length === 0 && (
                <div className="empty">No inspections yet for this park.</div>
              )}
            </div>
            {sortedInspections.length > 0 && (
              <p className="estimate-note">
                Est. loss/day is an estimate — {REVENUE_LOSS_NOTE.replace(/^Estimate: /, '')}
              </p>
            )}
            <section style={{ marginTop: 24 }}>
              <h2 style={{ fontSize: 16, fontWeight: 700, margin: '0 0 8px' }}>Anomaly Trend</h2>
              {trendLoading ? (
                <div style={{ height: 180, background: '#f1f5f9', borderRadius: 8 }} />
              ) : (
                <TrendChart data={trendData} />
              )}
            </section>
            {recurringData.length > 0 && (
              <section style={{ marginTop: 24 }}>
                <h2 style={{ fontSize: 16, fontWeight: 700, margin: '0 0 8px' }}>Recurring Faults</h2>
                <p style={{ fontSize: 12, color: '#64748b', marginBottom: 10 }}>
                  Panels with anomalies in 2 or more inspections.
                </p>
                <div className="table">
                  <div className="table-head hist-head">
                    <span>Panel</span>
                    <span>Flights</span>
                    <span>Fault Types</span>
                    <span>First</span>
                    <span>Severity</span>
                  </div>
                  {recurringData.map((row) => (
                    <div className="hist-row" key={row.panel_id}>
                      <span>
                        <strong>{row.panel_id}</strong>
                      </span>
                      <span>{row.inspection_count}</span>
                      <span>{row.classes.join(', ')}</span>
                      <span>{row.first_seen ?? '-'}</span>
                      <span>
                        <span className={`severity ${row.worst_severity.toLowerCase()}`}>
                          {row.worst_severity}
                        </span>
                      </span>
                    </div>
                  ))}
                </div>
              </section>
            )}
          </>
        )}
        {!historyLoading && !historyError && !parkSummary && (
          <div className="empty">Pick a park to see its history.</div>
        )}
      </section>
    </section>
  )
}
