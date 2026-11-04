// Terrain / AGL follow for the mission planner (roadmap A-phase-2).
// Pure offset math + a thin Open-Elevation client with graceful fallback:
// any API failure returns null and the mission keeps constant altitude.
import type { LatLon, Waypoint } from '@/lib/missionGeometry'

/** Never command below this relative altitude even over falling ground. */
export const MIN_SAFE_ALT_M = 5

const LOOKUP_URL = 'https://api.open-elevation.com/api/v1/lookup'
const BATCH_SIZE = 100
const TIMEOUT_MS = 15_000

/**
 * Re-base each waypoint's altitude so height-above-ground stays constant.
 * The first waypoint is the reference (its ground = launch ground level).
 * Falls back to the input untouched when elevations don't line up.
 */
export function applyTerrainOffsets(
  waypoints: Waypoint[],
  elevations: number[],
): Waypoint[] {
  if (waypoints.length === 0 || elevations.length !== waypoints.length) {
    return waypoints
  }
  const reference = elevations[0]
  return waypoints.map((w, i) => ({
    ...w,
    alt: Math.max(
      MIN_SAFE_ALT_M,
      Math.round((w.alt + (elevations[i] - reference)) * 10) / 10,
    ),
  }))
}

type LookupResult = { results?: { elevation: number }[] }

/**
 * Fetch ground elevation (m AMSL) for each point via Open-Elevation.
 * Returns null on ANY failure so callers can fall back to constant altitude.
 */
export async function fetchElevations(points: LatLon[]): Promise<number[] | null> {
  if (points.length === 0) return []
  const out: number[] = []
  try {
    for (let start = 0; start < points.length; start += BATCH_SIZE) {
      const batch = points.slice(start, start + BATCH_SIZE)
      const controller = new AbortController()
      const timer = setTimeout(() => controller.abort(), TIMEOUT_MS)
      let res: Response
      try {
        res = await fetch(LOOKUP_URL, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            locations: batch.map((p) => ({ latitude: p.lat, longitude: p.lon })),
          }),
          signal: controller.signal,
        })
      } finally {
        clearTimeout(timer)
      }
      if (!res.ok) return null
      const data = (await res.json()) as LookupResult
      const results = data.results ?? []
      if (results.length !== batch.length) return null
      for (const r of results) {
        if (typeof r.elevation !== 'number' || Number.isNaN(r.elevation)) return null
        out.push(r.elevation)
      }
    }
    return out
  } catch {
    return null
  }
}

/** Min/max altitude adjustment (m) terrain follow applied vs the flat plan. */
export function terrainDeltaRange(
  original: Waypoint[],
  adjusted: Waypoint[],
): { min: number; max: number } | null {
  if (original.length === 0 || original.length !== adjusted.length) return null
  let min = Infinity
  let max = -Infinity
  for (let i = 0; i < original.length; i++) {
    const d = adjusted[i].alt - original[i].alt
    if (d < min) min = d
    if (d > max) max = d
  }
  return { min: Math.round(min * 10) / 10, max: Math.round(max * 10) / 10 }
}
