'use client'

import type { TrendPoint } from '@/lib/api'

const COLORS = {
  CRITICAL: '#dc2626',
  HIGH: '#ea580c',
  MEDIUM: '#ca8a04',
  LOW: '#2563eb',
} as const

const MARGINS = { top: 16, right: 24, bottom: 36, left: 44 }
const VIEW_W = 720
const VIEW_H = 220
const CHART_W = VIEW_W - MARGINS.left - MARGINS.right
const CHART_H = VIEW_H - MARGINS.top - MARGINS.bottom

export function TrendChart({ data }: { data: TrendPoint[] }) {
  if (data.length < 2) {
    return (
      <div style={{ padding: 24, color: '#64748b', fontSize: 13, textAlign: 'center' }}>
        Need at least 2 inspections to show a trend.
      </div>
    )
  }

  const severities = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'] as const
  const maxCount = Math.max(1, ...data.flatMap((point) => severities.map((sev) => point[sev])))
  const yStep = niceStep(maxCount)
  const yMax = Math.ceil(maxCount / yStep) * yStep
  const yTicks = Array.from({ length: Math.ceil(yMax / yStep) + 1 }, (_, index) => index * yStep)

  function xPos(index: number) {
    return MARGINS.left + (index / (data.length - 1)) * CHART_W
  }

  function yPos(count: number) {
    return MARGINS.top + CHART_H - (count / yMax) * CHART_H
  }

  return (
    <svg
      viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
      preserveAspectRatio="xMinYMid meet"
      className="history-chart-svg"
      style={{ width: '100%', height: 'auto', display: 'block' }}
      role="img"
      aria-label="Anomaly trend over time"
    >
      {yTicks.map((tick) => (
        <g key={tick}>
          <line
            x1={MARGINS.left}
            y1={yPos(tick)}
            x2={MARGINS.left + CHART_W}
            y2={yPos(tick)}
            stroke="#e2e8f0"
            strokeWidth={1}
          />
          <text x={MARGINS.left - 6} y={yPos(tick) + 4} textAnchor="end" fontSize={10} fill="#94a3b8">
            {tick}
          </text>
        </g>
      ))}

      {data.map((point, index) => (
        <text
          key={point.inspection_id}
          x={xPos(index)}
          y={MARGINS.top + CHART_H + 20}
          textAnchor="middle"
          fontSize={10}
          fill="#64748b"
        >
          {point.date ? point.date.slice(5) : '?'}
        </text>
      ))}

      {severities.map((sev) => (
        <polyline
          key={sev}
          points={data.map((point, index) => `${xPos(index)},${yPos(point[sev])}`).join(' ')}
          fill="none"
          stroke={COLORS[sev]}
          strokeWidth={2}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      ))}

      {severities.map((sev) =>
        data.map((point, index) => (
          <circle key={`${sev}-${point.inspection_id}`} cx={xPos(index)} cy={yPos(point[sev])} r={3} fill={COLORS[sev]}>
            <title>{`${sev}: ${point[sev]} (${point.date ?? '?'})`}</title>
          </circle>
        )),
      )}

      {severities.map((sev, index) => (
        <g key={sev} transform={`translate(${MARGINS.left + index * 120}, ${VIEW_H - 6})`}>
          <rect x={0} y={-8} width={12} height={4} fill={COLORS[sev]} rx={1} />
          <text x={16} y={0} fontSize={10} fill="#64748b">
            {sev}
          </text>
        </g>
      ))}
    </svg>
  )
}

function niceStep(max: number): number {
  if (max <= 5) return 1
  if (max <= 20) return 5
  if (max <= 50) return 10
  return Math.ceil(max / 5 / 10) * 10
}
