import { describe, it, expect } from 'vitest'
import { computeCapturePoints, type Waypoint } from '@/lib/missionGeometry'

// A straight ~125m east-west leg near the equator-ish (Pune, India), matching
// the fixture style used in missionGeometry.test.ts.
const STRAIGHT_LEG: Waypoint[] = [
  { lat: 18.5200, lon: 73.8550, alt: 40 },
  { lat: 18.5200, lon: 73.8562, alt: 40 },
]

describe('computeCapturePoints', () => {
  it('returns empty array for fewer than 2 waypoints', () => {
    expect(computeCapturePoints([{ lat: 0, lon: 0, alt: 40 }], 10)).toEqual([])
  })

  it('returns empty array for non-positive trigger distance', () => {
    expect(computeCapturePoints(STRAIGHT_LEG, 0)).toEqual([])
    expect(computeCapturePoints(STRAIGHT_LEG, -5)).toEqual([])
  })

  it('places points at the trigger-distance interval along a straight segment', () => {
    const points = computeCapturePoints(STRAIGHT_LEG, 25)
    expect(points.length).toBeGreaterThan(3)
    for (let i = 1; i < points.length; i++) {
      const dLat = (points[i].lat - points[i - 1].lat) * 111320
      const dLon = (points[i].lon - points[i - 1].lon) * 111320 * Math.cos((points[i].lat * Math.PI) / 180)
      const dist = Math.hypot(dLat, dLon)
      expect(dist).toBeGreaterThan(20)
      expect(dist).toBeLessThan(30)
    }
  })

  it('interpolates altitude and carries a heading for every point', () => {
    const points = computeCapturePoints(STRAIGHT_LEG, 25)
    for (const p of points) {
      expect(p.alt).toBeCloseTo(40, 5)
      expect(p.heading).toBeDefined()
    }
  })

  it('carries leftover distance across multiple segments without double-counting', () => {
    const threeLegPath: Waypoint[] = [
      { lat: 18.5200, lon: 73.8550, alt: 40 },
      { lat: 18.5200, lon: 73.8556, alt: 40 },
      { lat: 18.5200, lon: 73.8562, alt: 40 },
    ]
    const singleSegment = computeCapturePoints(STRAIGHT_LEG, 25)
    const multiSegment = computeCapturePoints(threeLegPath, 25)
    expect(multiSegment.length).toBe(singleSegment.length)
  })
})
