/** Manual park layout status helpers (Park Map tab). */

export type ParkLayoutSummary = {
  park_id: string | null
  name: string | null
  tables: number
  total_panels: number
  match_tolerance_m: number
  source_format: 'layout' | 'geojson'
}

export type ParkLayoutStatus = {
  park_id?: string
  mode: 'auto' | 'manual'
  summary: ParkLayoutSummary | null
  layout?: unknown
  error: string | null
}

export function layoutModeLabel(
  status: Pick<ParkLayoutStatus, 'mode' | 'summary' | 'error'> | null,
): string {
  if (!status) return '—'
  if (status.mode !== 'manual') return 'Auto-grid'
  if (status.error || !status.summary) return 'Manual · invalid'
  return `Manual · ${status.summary.total_panels} panels / ${status.summary.tables} tables`
}

/** Which upload format a filename implies, or null when it is not a layout file. */
export function layoutFileKind(filename: string): 'layout' | 'geojson' | null {
  const lower = filename.toLowerCase()
  if (lower.endsWith('.geojson')) return 'geojson'
  if (lower.endsWith('.json')) return 'layout'
  return null
}
