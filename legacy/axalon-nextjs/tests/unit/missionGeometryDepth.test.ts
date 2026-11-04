import { describe, it, expect } from 'vitest'
import {
  generateOrbit, splitByBattery, bearingDeg, generateGrid, computeStats,
  type MissionParams, type Waypoint,
} from '@/lib/missionGeometry'
import { toLitchiCsv, serialiseQGCWPL110 } from '@/lib/waypointExport'
import { DEFAULT_CAMERA } from '@/lib/cameras'

const cam = DEFAULT_CAMERA
const base: MissionParams = {
  altitudeM: 40, frontOverlap: 0.8, sideOverlap: 0.7, speedMs: 8, headingDeg: 'auto',
  batteryMinutes: 18, batteryReservePct: 20, orbitRadiusM: 30, orbitPhotoCount: 12,
}

describe('generateOrbit', () => {
  it('produces orbitPhotoCount waypoints aimed at center with a downward gimbal', () => {
    const center = { lat: 18.52, lon: 73.85 }
    const wps = generateOrbit(center, cam, base)
    expect(wps.length).toBe(12)
    const expectedPitch = -((Math.atan2(40, 30) * 180) / Math.PI)
    for (const w of wps) {
      expect(w.gimbalPitch).toBeCloseTo(expectedPitch, 3)
      expect(typeof w.heading).toBe('number')
    }
    // each waypoint heading points toward the center
    expect(wps[0].heading).toBeCloseTo(bearingDeg(wps[0], center), 3)
  })
})

describe('splitByBattery', () => {
  it('splits into multiple legs when the path exceeds the budget', () => {
    const wps: Waypoint[] = Array.from({ length: 6 }, (_, i) => ({ lat: 18.5 + i * 0.01, lon: 73.8, alt: 40 }))
    const r = splitByBattery(wps, { ...base, batteryMinutes: 5, batteryReservePct: 0, speedMs: 8 })
    expect(r.legCount).toBeGreaterThan(1)
    for (let i = 1; i < r.waypoints.length; i++) {
      expect(r.waypoints[i].leg ?? 0).toBeGreaterThanOrEqual(r.waypoints[i - 1].leg ?? 0)
    }
  })

  it('is a single leg when the budget is ample', () => {
    const wps: Waypoint[] = [{ lat: 18.5, lon: 73.8, alt: 40 }, { lat: 18.5001, lon: 73.8, alt: 40 }]
    expect(splitByBattery(wps, { ...base, batteryMinutes: 30 }).legCount).toBe(1)
  })
})

describe('generateGrid (α alignment)', () => {
  it('emits per-waypoint travel headings', () => {
    const poly = [
      { lat: 18.52, lon: 73.85 }, { lat: 18.52, lon: 73.86 },
      { lat: 18.525, lon: 73.86 }, { lat: 18.525, lon: 73.85 },
    ]
    const wps = generateGrid(poly, cam, { ...base, headingDeg: 90 })
    expect(wps.length).toBeGreaterThan(2)
    expect(typeof wps[1].heading).toBe('number')
  })
})

describe('computeStats batteries', () => {
  it('includes legCount and batteryCount', () => {
    const poly = [
      { lat: 18.52, lon: 73.85 }, { lat: 18.52, lon: 73.86 },
      { lat: 18.525, lon: 73.86 }, { lat: 18.525, lon: 73.85 },
    ]
    const wps = generateGrid(poly, cam, base)
    const s = computeStats(wps, poly, cam, base)
    expect(s.batteryCount).toBe(s.legCount)
    expect(s.legCount).toBeGreaterThanOrEqual(1)
  })
})

describe('export carries heading + battery legs', () => {
  it('litchi heading column reflects waypoint heading', () => {
    const wps: Waypoint[] = [
      { lat: 1, lon: 2, alt: 40, heading: 90 },
      { lat: 1.001, lon: 2, alt: 40, heading: 270 },
    ]
    const rows = toLitchiCsv(wps, base, 2).split('\n')
    expect(rows[1].split(',')[3]).toBe('90') // heading(deg) is column index 3
  })

  it('WPL110 inserts an RTL between battery legs', () => {
    const wps: Waypoint[] = [
      { lat: 1, lon: 2, alt: 40, leg: 0 },
      { lat: 1.1, lon: 2, alt: 40, leg: 0 },
      { lat: 1.2, lon: 2, alt: 40, leg: 1 },
    ]
    const text = serialiseQGCWPL110(wps, 5)
    const rtlCount = text.split('\n').filter((l) => l.split('\t')[3] === '20').length
    expect(rtlCount).toBe(2) // one at the leg break + the final RTL
  })
})
