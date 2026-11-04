'use client'

import { formatDeltaT, formatTempC, type ThermalFields } from '@/lib/thermalFormat'

/** Max temperature + ΔT for one detection. Renders nothing without radiometric data. */
export function ThermalReadout({ max_temp, delta_t_measured }: ThermalFields) {
  const max = formatTempC(max_temp)
  const dt = formatDeltaT(delta_t_measured)
  if (!max && !dt) return null
  return (
    <span
      className="thermal-readout"
      title="Radiometric: ΔT = hotspot max − frame median (reference module)"
    >
      {max && (
        <span>
          <span className="tr-label">max</span>
          {max}
        </span>
      )}
      {dt && <span className="tr-dt">{dt}</span>}
    </span>
  )
}
