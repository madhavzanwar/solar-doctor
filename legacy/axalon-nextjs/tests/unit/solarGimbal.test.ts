import { describe, it, expect } from 'vitest'
import { generateSolar, generateGrid, resolvedHeadingDeg, type MissionParams } from '@/lib/missionGeometry'
import { DEFAULT_CAMERA } from '@/lib/cameras'

const cam = DEFAULT_CAMERA
const base: MissionParams = {
  altitudeM: 30, frontOverlap: 0.8, sideOverlap: 0.7, speedMs: 8, headingDeg: 'auto', gimbalPitchDeg: -45,
}

describe('generateSolar', () => {
  const area = [
    { lat: 18.5, lon: 73.8 },
    { lat: 18.5, lon: 73.802 },
    { lat: 18.501, lon: 73.802 },
    { lat: 18.501, lon: 73.8 },
  ]
  const rows = [
    { lat: 18.5002, lon: 73.801 },
    { lat: 18.5007, lon: 73.801 },
  ]

  it('emits 2 clipped waypoints per clicked row with the configured gimbal', () => {
    const wps = generateSolar(area, rows, { ...base, rowAngleDeg: 0 })
    expect(wps.length).toBe(rows.length * 2)
    for (const w of wps) expect(w.gimbalPitch).toBe(-45)
    for (const w of wps) {
      expect(w.lat).toBeGreaterThanOrEqual(18.5)
      expect(w.lat).toBeLessThanOrEqual(18.501)
      expect(w.lon).toBeGreaterThanOrEqual(73.8)
      expect(w.lon).toBeLessThanOrEqual(73.802)
    }
  })

  it('changes endpoint orientation when row angle α changes', () => {
    const flat = generateSolar(area, [rows[0]], { ...base, rowAngleDeg: 0 })
    const angled = generateSolar(area, [rows[0]], { ...base, rowAngleDeg: 45 })
    expect(Math.abs(flat[1].lat - flat[0].lat)).toBeLessThan(0.00001)
    expect(Math.abs(angled[1].lat - angled[0].lat)).toBeGreaterThan(0.0001)
    expect(Math.abs(angled[1].lon - angled[0].lon)).toBeGreaterThan(0.0001)
  })

  it('supports a fixed drone orientation heading', () => {
    const wps = generateSolar(area, [rows[0]], { ...base, droneHeadingDeg: 123 })
    expect(wps.map((w) => w.heading)).toEqual([123, 123])
  })

  it('returns empty without an area or without rows', () => {
    expect(generateSolar([{ lat: 1, lon: 1 }, { lat: 1, lon: 2 }], [{ lat: 1, lon: 1 }], base)).toHaveLength(0)
    expect(generateSolar(area, [], base)).toHaveLength(0)
  })
})

describe('grid gimbal', () => {
  it('stamps gimbalPitchDeg on grid waypoints', () => {
    const poly = [{ lat: 18.52, lon: 73.85 }, { lat: 18.52, lon: 73.86 }, { lat: 18.525, lon: 73.86 }, { lat: 18.525, lon: 73.85 }]
    expect(generateGrid(poly, cam, base)[0].gimbalPitch).toBe(-45)
  })
})

describe('resolvedHeadingDeg', () => {
  it('returns the numeric angle, or a number for auto', () => {
    const poly = [{ lat: 18.52, lon: 73.85 }, { lat: 18.52, lon: 73.86 }, { lat: 18.525, lon: 73.86 }]
    expect(resolvedHeadingDeg(poly, { ...base, headingDeg: 90 })).toBe(90)
    expect(typeof resolvedHeadingDeg(poly, { ...base, headingDeg: 'auto' })).toBe('number')
  })
})
