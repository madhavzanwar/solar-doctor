/** Presentation helpers for the thermal↔RGB rig calibration (Settings tab). */

export type CalibrationSource = 'env' | 'settings' | 'database' | null

export type CalibrationSummary = {
  rig_id: string
  thermal_camera?: string | null
  rgb_camera?: string | null
  thermal_size?: [number, number]
  rgb_size?: [number, number]
  rms_error_px: number
  num_points?: number | null
  method?: string | null
  created_at?: string
}

export type CalibrationStatus = {
  configured: boolean
  source: CalibrationSource
  path: string | null
  error: string | null
  calibration: CalibrationSummary | null
}

// Reprojection error in RGB pixels. Under ~2 px a thermal box lands on the
// right panel cell; past ~5 px the calibration should be re-picked.
const RMS_GOOD_PX = 2
const RMS_USABLE_PX = 5

export function rmsTone(rms: number | null | undefined): 'ok' | 'info' | 'crit' | 'muted' {
  if (rms === null || rms === undefined || !Number.isFinite(rms)) return 'muted'
  if (rms <= RMS_GOOD_PX) return 'ok'
  if (rms <= RMS_USABLE_PX) return 'info'
  return 'crit'
}

export function calibrationSourceLabel(source: CalibrationSource): string {
  switch (source) {
    case 'env':
      return 'AXALON_FUSION_CALIBRATION (env override)'
    case 'settings':
      return 'settings.yaml camera.fusion_calibration'
    case 'database':
      return 'Uploaded via Settings'
    default:
      return 'Not configured'
  }
}
