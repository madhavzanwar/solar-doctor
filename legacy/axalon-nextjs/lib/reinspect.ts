// website/nextjs/lib/reinspect.ts
// Turn an inspection's detected faults into a targeted re-fly mission. Pure + tested.
import { bearingDeg, type Waypoint } from './missionGeometry'
import type { Severity } from './analytics'

export type FaultPoint = { lat: number; lon: number; severity: Severity }
export type ReinspectOptions = { altitudeM: number; minSeverity: Severity }

const RANK: Record<Severity, number> = { CRITICAL: 4, HIGH: 3, MEDIUM: 2, LOW: 1 }

function normSeverity(s: unknown): Severity {
  const up = String(s ?? '').toUpperCase()
  return up === 'CRITICAL' || up === 'HIGH' || up === 'MEDIUM' || up === 'LOW' ? (up as Severity) : 'LOW'
}

function distM(a: FaultPoint, b: FaultPoint): number {
  const R = 6371000
  const dLat = ((b.lat - a.lat) * Math.PI) / 180
  const dLon = ((b.lon - a.lon) * Math.PI) / 180
  const la = (a.lat * Math.PI) / 180
  const lb = (b.lat * Math.PI) / 180
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(la) * Math.cos(lb) * Math.sin(dLon / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(h))
}

// Defensively extract fault points from a loosely-typed /map response
// (handles { anomalies: [...] } / { detections: [...] } / GeoJSON features / bare arrays).
export function faultsFromMapData(data: unknown): FaultPoint[] {
  const d = data as any
  const arr: any[] =
    Array.isArray(d?.anomalies) ? d.anomalies
      : Array.isArray(d?.detections) ? d.detections
        : Array.isArray(d?.features) ? d.features
          : Array.isArray(d) ? d
            : []
  const out: FaultPoint[] = []
  for (const it of arr) {
    let lat: unknown
    let lon: unknown
    let sev: unknown
    if (it?.geometry?.coordinates) {
      lon = it.geometry.coordinates[0]
      lat = it.geometry.coordinates[1]
      sev = it.properties?.severity
    } else {
      lat = it?.lat
      lon = it?.lon ?? it?.lng
      sev = it?.severity
    }
    const la = Number(lat)
    const lo = Number(lon)
    if (Number.isFinite(la) && Number.isFinite(lo)) out.push({ lat: la, lon: lo, severity: normSeverity(sev) })
  }
  return out
}

// Filter faults at/above minSeverity, order them greedily (nearest-neighbour) for an
// efficient re-fly path, and assign travel headings.
export function planReinspection(faults: FaultPoint[], opts: ReinspectOptions): Waypoint[] {
  const minRank = RANK[opts.minSeverity]
  const pts = faults.filter((f) => RANK[f.severity] >= minRank)
  if (pts.length === 0) return []

  const remaining = pts.slice()
  const ordered: FaultPoint[] = [remaining.shift() as FaultPoint]
  while (remaining.length) {
    const last = ordered[ordered.length - 1]
    let bestIdx = 0
    let bestDist = Infinity
    for (let i = 0; i < remaining.length; i++) {
      const dist = distM(last, remaining[i])
      if (dist < bestDist) {
        bestDist = dist
        bestIdx = i
      }
    }
    ordered.push(remaining.splice(bestIdx, 1)[0])
  }

  return ordered.map((p, i) => {
    const next = ordered[i + 1]
    const heading = next ? bearingDeg(p, next) : i > 0 ? bearingDeg(ordered[i - 1], p) : 0
    return { lat: p.lat, lon: p.lon, alt: opts.altitudeM, heading }
  })
}
