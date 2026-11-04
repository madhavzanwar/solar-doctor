import { describe, expect, test } from 'vitest'

import { routeBounds, routeLatLngs, routeMarkers, shouldFitToRoute } from '@/lib/liveRoute'

const route = [
  { lat: 18.52, lon: 73.85, altitude: 40 },
  { lat: 18.53, lon: 73.86 },
  { lat: 18.51, lon: 73.87, altitude: 42 },
]

describe('routeLatLngs', () => {
  test('converts planned points to Leaflet [lat, lng] pairs in order', () => {
    expect(routeLatLngs(route)).toEqual([
      [18.52, 73.85],
      [18.53, 73.86],
      [18.51, 73.87],
    ])
  })

  test('drops points without finite coordinates', () => {
    expect(routeLatLngs([{ lat: Number.NaN, lon: 1 }, { lat: 2, lon: 3 }])).toEqual([[2, 3]])
  })
})

describe('routeBounds', () => {
  test('returns the south-west and north-east corners', () => {
    expect(routeBounds(route)).toEqual([
      [18.51, 73.85],
      [18.53, 73.87],
    ])
  })

  test('is null for an empty route', () => {
    expect(routeBounds([])).toBeNull()
  })
})

describe('routeMarkers', () => {
  test('labels start, numbered waypoints and end', () => {
    expect(routeMarkers(route)).toEqual([
      { latlng: [18.52, 73.85], label: 'S', kind: 'start' },
      { latlng: [18.53, 73.86], label: '2', kind: 'waypoint' },
      { latlng: [18.51, 73.87], label: 'E', kind: 'end' },
    ])
  })

  test('a single point is just the start', () => {
    expect(routeMarkers([route[0]])).toEqual([{ latlng: [18.52, 73.85], label: 'S', kind: 'start' }])
  })

  test('long routes keep only start and end so the map stays readable', () => {
    const long = Array.from({ length: 10 }, (_, i) => ({ lat: i, lon: i }))
    expect(routeMarkers(long, 5).map((m) => m.label)).toEqual(['S', 'E'])
    expect(routeMarkers(long, 10)).toHaveLength(10)
  })

  test('is empty for an empty route', () => {
    expect(routeMarkers([])).toEqual([])
  })
})

describe('shouldFitToRoute', () => {
  test('fits the first time a route appears before any telemetry', () => {
    expect(shouldFitToRoute({ routeLength: 3, hasTelemetry: false, alreadyFitted: false })).toBe(true)
  })

  test('never fights the follow-drone view or refits an unchanged route', () => {
    expect(shouldFitToRoute({ routeLength: 3, hasTelemetry: true, alreadyFitted: false })).toBe(false)
    expect(shouldFitToRoute({ routeLength: 3, hasTelemetry: false, alreadyFitted: true })).toBe(false)
    expect(shouldFitToRoute({ routeLength: 0, hasTelemetry: false, alreadyFitted: false })).toBe(false)
  })
})
