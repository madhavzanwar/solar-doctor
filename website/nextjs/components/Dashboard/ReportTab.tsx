'use client'

import { D } from './tokens'

const panelStyle: React.CSSProperties = {
  flex: '1 1 0',
  minWidth: 0,
  border: `1px solid ${D.panelBorder}`,
  borderRadius: 6,
  background: D.panelBg,
  padding: '1.75rem',
  fontFamily: D.mono,
  fontSize: '0.8rem',
  lineHeight: 1.7,
  whiteSpace: 'pre-wrap',
  overflow: 'auto',
}

const labelCol = { color: D.muted }
const accent = { color: D.teal, fontWeight: 700 }

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', gap: '0.75rem' }}>
      <span style={{ ...labelCol, minWidth: 84, display: 'inline-block' }}>{label}</span>
      <span>{value}</span>
    </div>
  )
}

function WorkOrderRow({
  id,
  string,
  type,
  dt,
  action,
  critical,
}: {
  id: string
  string: string
  type: string
  dt: string
  action: string
  critical?: boolean
}) {
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'auto auto 1fr auto auto',
        gap: '0.75rem',
        padding: '0.35rem 0.5rem',
        margin: '0 -0.5rem',
        background: critical ? D.redTint : undefined,
        borderLeft: critical ? `2px solid ${D.red}` : '2px solid transparent',
        color: critical ? D.text : undefined,
      }}
    >
      <span style={{ color: critical ? D.red : D.teal, fontWeight: 700 }}>{id}</span>
      <span style={labelCol}>{string}</span>
      <span>{type}</span>
      <span style={labelCol}>{dt}</span>
      <span style={{ fontWeight: 700 }}>{action}</span>
    </div>
  )
}

export function ReportTab() {
  return (
    <div
      style={{
        display: 'flex',
        gap: '2rem',
        height: '100%',
        padding: '2rem 2.5rem',
        alignItems: 'stretch',
      }}
    >
      {/* ── Left: email ──────────────────────────────────── */}
      <div style={panelStyle}>
        <div style={{ ...accent, marginBottom: '1rem', letterSpacing: '0.1em' }}>AUTOMATED EMAIL</div>
        <Field label="FROM:" value="axa9@axalonsystems.in" />
        <Field label="TO:" value="substation.incharge@solarpark.in" />
        <Field label="CC:" value="o&m.manager@solarpark.in" />
        <Field
          label="SUBJECT:"
          value={<span>[AUTO] Thermography Report — Block 04 | 42 Defects Detected | 01 June 2026</span>}
        />
        <div style={{ marginTop: '1.25rem' }}>
          {`Dear Sir/Madam,

AXA-9 has completed autonomous thermal inspection of Block 04
(15.2 MW) at 13:42 IST on 01 June 2026.

MISSION SUMMARY:
- Panels Scanned       : 7,200
- Defects Detected     : 42
- Critical Hotspots    : 8
- Estimated Yield Loss : 2.3%

Full thermographic report and defect map attached.
Work order WO-2026-0601-B04 has been auto-generated.

Regards,
AXA-9 Autonomous Inspection System
AXALON Systems Pvt. Ltd.`}
        </div>
      </div>

      {/* ── Right: work order ────────────────────────────── */}
      <div style={panelStyle}>
        <div style={{ ...accent, marginBottom: '1rem', letterSpacing: '0.1em' }}>WORK ORDER</div>
        <div style={{ fontWeight: 700, marginBottom: '1.25rem' }}>WO-2026-0601-B04</div>
        <Field label="SITE:" value="Solar Park Block 04" />
        <Field label="DATE:" value="01 June 2026" />
        <Field label="PRIORITY:" value={<span style={{ color: D.red, fontWeight: 700 }}>HIGH</span>} />

        <div style={{ ...labelCol, margin: '1.25rem 0 0.5rem' }}>DEFECTS REQUIRING ATTENTION:</div>
        <WorkOrderRow id="D-07" string="STRING 07" type="HOTSPOT" dt="ΔT +24°C" action="REPLACE CELL" critical />
        <WorkOrderRow id="D-12" string="STRING 12" type="DIODE FAILURE" dt="ΔT +18°C" action="REPLACE DIODE" critical />
        <WorkOrderRow id="D-19" string="STRING 03" type="CELL CRACK" dt="ΔT +11°C" action="INSPECT STRING" />

        <div style={{ marginTop: '1.25rem' }}>
          <Field label="ASSIGNED:" value="Field Maintenance Team" />
          <Field label="TARGET:" value="03 June 2026" />
          <Field label="STATUS:" value={<span style={accent}>OPEN</span>} />
        </div>

        <div style={{ ...labelCol, marginTop: '1.25rem', fontSize: '0.72rem' }}>
          {`Generated automatically by AXA-9 Edge AI
AXALON Systems Pvt. Ltd.`}
        </div>
      </div>
    </div>
  )
}
