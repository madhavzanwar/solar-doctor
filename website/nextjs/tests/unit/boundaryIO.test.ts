import { describe, it, expect } from 'vitest'
import { parseGeoJson, parseKml, parseBoundary, toGeoJson, toKml } from '@/lib/boundaryIO'

const pts = [
  { lat: 18.52, lon: 73.85 },
  { lat: 18.52, lon: 73.86 },
  { lat: 18.525, lon: 73.86 },
  { lat: 18.525, lon: 73.85 },
]

describe('GeoJSON', () => {
  it('round-trips a polygon (closing dup dropped)', () => {
    const back = parseGeoJson(toGeoJson(pts))
    expect(back.length).toBe(pts.length)
    expect(back[0].lat).toBeCloseTo(pts[0].lat, 6)
    expect(back[1].lon).toBeCloseTo(pts[1].lon, 6)
  })

  it('reads a FeatureCollection', () => {
    const fc = JSON.stringify({
      type: 'FeatureCollection',
      features: [{
        type: 'Feature',
        geometry: { type: 'Polygon', coordinates: [[[73.85, 18.52], [73.86, 18.52], [73.86, 18.525], [73.85, 18.52]]] },
      }],
    })
    expect(parseGeoJson(fc).length).toBe(3)
  })
})

describe('KML', () => {
  it('round-trips a polygon', () => {
    const back = parseKml(toKml(pts))
    expect(back.length).toBe(pts.length)
    expect(back[2].lat).toBeCloseTo(pts[2].lat, 6)
  })
})

describe('parseBoundary', () => {
  it('dispatches KML by extension and GeoJSON otherwise', () => {
    expect(parseBoundary(toKml(pts), 'site.kml').length).toBe(pts.length)
    expect(parseBoundary(toGeoJson(pts), 'site.geojson').length).toBe(pts.length)
  })

  it('throws on too few points', () => {
    expect(() => parseBoundary(JSON.stringify({ type: 'LineString', coordinates: [[73.85, 18.52]] }), 'x.geojson')).toThrow()
  })
})
