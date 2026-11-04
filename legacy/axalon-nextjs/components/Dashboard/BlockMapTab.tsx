'use client'

import { D } from './tokens'

// 40 cols × 18 rows = 720 cells; each cell = 10 panels → 7,200 panels.
const COLS = 40
const ROWS = 18
const TOTAL = COLS * ROWS

// Fixed scatter (not randomized) so the map is stable across renders.
const RED = [47, 123, 198, 256, 341, 489, 552, 667] // 8 critical
const YELLOW = [
  8, 12, 34, 78, 105, 160, 215, 230, 288, 310, 367, 402, 433, 470, 510, 540,
  580, 615, 640, 690, 705,
] // 21 moderate

const redSet = new Set(RED)
const yellowSet = new Set(YELLOW)

const stats: Array<[string, string]> = [
  ['TOTAL PANELS SCANNED', '7,200'],
  ['DEFECTS DETECTED', '42'],
  ['CRITICAL HOTSPOTS', '8'],
  ['BYPASS DIODE FAILURES', '21'],
  ['CELL CRACKS', '13'],
  ['ESTIMATED YIELD LOSS', '2.3%'],
  ['MISSION DURATION', '00:47:23'],
  ['COVERAGE', '100%'],
]

const defects: Array<{
  id: string
  type: string
  string: string
  dt: string
  severity: 'CRITICAL' | 'MODERATE'
}> = [
  { id: 'D-07', type: 'HOTSPOT', string: 'STRING 07', dt: 'ΔT +24°C', severity: 'CRITICAL' },
  { id: 'D-12', type: 'DIODE FAILURE', string: 'STRING 12', dt: 'ΔT +18°C', severity: 'CRITICAL' },
  { id: 'D-19', type: 'CELL CRACK', string: 'STRING 03', dt: 'ΔT +11°C', severity: 'MODERATE' },
]

function Swatch({ color }: { color: string }) {
  return (
    <span
      style={{
        display: 'inline-block',
        width: 10,
        height: 10,
        borderRadius: 2,
        background: color,
        marginRight: 8,
        verticalAlign: 'middle',
      }}
    />
  )
}

export function BlockMapTab() {
  return (
    <div
      style={{
        display: 'flex',
        gap: '2.5rem',
        height: '100%',
        padding: '2rem 2.5rem',
        alignItems: 'stretch',
        fontFamily: D.mono,
      }}
    >
      {/* ── Left: panel grid ─────────────────────────────── */}
      <div style={{ flex: '0 0 auto', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
        <div style={{ fontSize: '0.65rem', letterSpacing: '0.18em', color: D.muted, marginBottom: '0.9rem' }}>
          BLOCK 04 — PANEL THERMOGRAPHY MAP
        </div>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: `repeat(${COLS}, 14px)`,
            gridAutoRows: '14px',
            gap: 2,
          }}
        >
          {Array.from({ length: TOTAL }, (_, i) => {
            const color = redSet.has(i) ? D.red : yellowSet.has(i) ? D.yellow : D.blue
            const critical = redSet.has(i)
            return (
              <div
                key={i}
                style={{
                  width: 14,
                  height: 14,
                  borderRadius: 2,
                  background: color,
                  opacity: critical ? 1 : 0.85,
                  boxShadow: critical ? `0 0 6px ${D.red}` : undefined,
                }}
              />
            )
          })}
        </div>
        {/* Legend */}
        <div style={{ display: 'flex', gap: '1.75rem', marginTop: '1.25rem', fontSize: '0.62rem', letterSpacing: '0.12em', color: D.muted }}>
          <span><Swatch color={D.blue} />HEALTHY</span>
          <span><Swatch color={D.yellow} />MODERATE ANOMALY</span>
          <span><Swatch color={D.red} />CRITICAL HOTSPOT</span>
        </div>
      </div>

      {/* ── Centre: summary stats ────────────────────────── */}
      <div style={{ flex: '1 1 0', display: 'flex', flexDirection: 'column', justifyContent: 'center', minWidth: 0 }}>
        <div style={{ fontSize: '0.65rem', letterSpacing: '0.18em', color: D.muted, marginBottom: '1.1rem' }}>
          MISSION SUMMARY
        </div>
        {stats.map(([label, value]) => (
          <div
            key={label}
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              gap: '1.5rem',
              padding: '0.5rem 0',
              borderBottom: `1px solid ${D.panelBorder}`,
              fontSize: '0.8rem',
            }}
          >
            <span style={{ color: D.muted }}>{label}</span>
            <span style={{ color: D.teal, fontWeight: 700 }}>{value}</span>
          </div>
        ))}
      </div>

      {/* ── Right: top defects ───────────────────────────── */}
      <div style={{ flex: '1 1 0', display: 'flex', flexDirection: 'column', justifyContent: 'center', minWidth: 0 }}>
        <div style={{ fontSize: '0.65rem', letterSpacing: '0.18em', color: D.muted, marginBottom: '1.1rem' }}>
          TOP DEFECTS
        </div>
        {defects.map((d) => (
          <div
            key={d.id}
            style={{
              display: 'grid',
              gridTemplateColumns: 'auto 1fr auto',
              gap: '0.4rem 1rem',
              padding: '0.7rem 0',
              borderBottom: `1px solid ${D.panelBorder}`,
              fontSize: '0.78rem',
              alignItems: 'center',
            }}
          >
            <span style={{ color: D.teal, fontWeight: 700 }}>{d.id}</span>
            <span>{d.type}</span>
            <span style={{ color: D.muted }}>{d.string}</span>
            <span />
            <span style={{ color: D.muted }}>{d.dt}</span>
            <span style={{ whiteSpace: 'nowrap' }}>
              <Swatch color={d.severity === 'CRITICAL' ? D.red : D.yellow} />
              <span style={{ color: d.severity === 'CRITICAL' ? D.red : D.yellow, fontWeight: 700 }}>
                {d.severity}
              </span>
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
