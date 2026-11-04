// website/nextjs/lib/boundaryIO.ts
// Import/export a survey-area boundary as GeoJSON or KML. Pure + browser/jsdom safe.
import type { LatLon } from './missionGeometry'

function clampPts(pts: LatLon[]): LatLon[] {
  return pts.filter(
    (p) => Number.isFinite(p.lat) && Number.isFinite(p.lon) &&
      p.lat >= -90 && p.lat <= 90 && p.lon >= -180 && p.lon <= 180,
  )
}

// GeoJSON polygons repeat the first point to close the ring — drop that dup.
function dropClosing(pts: LatLon[]): LatLon[] {
  if (pts.length > 1) {
    const a = pts[0]
    const b = pts[pts.length - 1]
    if (Math.abs(a.lat - b.lat) < 1e-9 && Math.abs(a.lon - b.lon) < 1e-9) return pts.slice(0, -1)
  }
  return pts
}

// coords: array of [lon, lat, (alt)]
function ringFromCoords(coords: unknown): LatLon[] {
  if (!Array.isArray(coords)) return []
  return coords
    .filter((c): c is number[] => Array.isArray(c) && c.length >= 2)
    .map((c) => ({ lat: Number(c[1]), lon: Number(c[0]) }))
}

export function parseGeoJson(text: string): LatLon[] {
  const data = JSON.parse(text)
  const geoms: any[] = []
  const collect = (g: any): void => {
    if (!g) return
    if (g.type === 'FeatureCollection') (g.features ?? []).forEach((f: any) => collect(f))
    else if (g.type === 'Feature') collect(g.geometry)
    else geoms.push(g)
  }
  collect(data)
  for (const g of geoms) {
    if (g.type === 'Polygon') return dropClosing(clampPts(ringFromCoords(g.coordinates?.[0])))
    if (g.type === 'MultiPolygon') return dropClosing(clampPts(ringFromCoords(g.coordinates?.[0]?.[0])))
    if (g.type === 'LineString') return dropClosing(clampPts(ringFromCoords(g.coordinates)))
  }
  return []
}

export function parseKml(text: string): LatLon[] {
  const doc = new DOMParser().parseFromString(text, 'application/xml')
  const node = doc.getElementsByTagName('coordinates')[0]
  if (!node || !node.textContent) return []
  const pts = node.textContent
    .trim()
    .split(/\s+/)
    .map((tok) => {
      const [lon, lat] = tok.split(',').map(Number)
      return { lat, lon }
    })
  return dropClosing(clampPts(pts))
}

export function parseBoundary(text: string, filename = ''): LatLon[] {
  const isKml = /\.kml$/i.test(filename) || /<kml[\s>]/i.test(text)
  const pts = isKml ? parseKml(text) : parseGeoJson(text)
  if (pts.length < 3) {
    throw new Error(`Boundary needs at least 3 points (parsed ${pts.length})`)
  }
  return pts
}

export function toGeoJson(points: LatLon[]): string {
  const ring = [...points, points[0]].map((p) => [p.lon, p.lat]) // close the ring
  return JSON.stringify(
    {
      type: 'Feature',
      properties: { name: 'Axalon site boundary' },
      geometry: { type: 'Polygon', coordinates: [ring] },
    },
    null,
    2,
  )
}

export function toKml(points: LatLon[]): string {
  const coords = [...points, points[0]].map((p) => `${p.lon},${p.lat},0`).join(' ')
  return `<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>Axalon site boundary</name>
<Placemark><name>Boundary</name><Polygon><outerBoundaryIs><LinearRing>
<coordinates>${coords}</coordinates>
</LinearRing></outerBoundaryIs></Polygon></Placemark>
</Document></kml>`
}
