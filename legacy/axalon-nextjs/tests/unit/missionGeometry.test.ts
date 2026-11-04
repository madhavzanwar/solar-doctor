import { describe, it, expect } from 'vitest'
import {
  generateGrid,
  generatePerimeter,
  generateCorridor,
  computeStats,
  computeFootprint,
  type LatLon,
  type MissionParams,
} from '@/lib/missionGeometry'
import { DEFAULT_CAMERA } from '@/lib/cameras'

// ~200m × ~200m square near the equator-ish (Pune, India)
const SQUARE: LatLon[] = [
  { lat: 18.5200, lon: 73.8550 },
  { lat: 18.5200, lon: 73.8569 },
  { lat: 18.5182, lon: 73.8569 },
  { lat: 18.5182, lon: 73.8550 },
]

const PARAMS: MissionParams = {
  altitudeM: 20,
  frontOverlap: 0.8,
  sideOverlap: 0.7,
  speedMs: 8,
  headingDeg: 'auto',
}

describe('computeFootprint', () => {
  it('computes footprint width/height in metres at altitude', () => {
    // footprint_w_m = altM * sensorWidthMm / focalLengthMm = 20 * 7.68 / 25 = 6.144 m
    const fp = computeFootprint(DEFAULT_CAMERA, PARAMS)
    expect(fp.w).toBeCloseTo(6.144, 2)
    expect(fp.h).toBeCloseTo(4.9152, 2)
  })
})

describe('generateGrid', () => {
  it('returns a non-empty waypoint list with takeoff first and altitude set', () => {
    const wps = generateGrid(SQUARE, DEFAULT_CAMERA, PARAMS)
    expect(wps.length).toBeGreaterThan(2)
    // first waypoint is takeoff at polygon vertex[0]
    expect(wps[0].lat).toBeCloseTo(SQUARE[0].lat, 4)
    expect(wps[0].lon).toBeCloseTo(SQUARE[0].lon, 4)
    // all waypoints carry the flight altitude
    for (const wp of wps) expect(wp.alt).toBe(20)
  })

  it('keeps all survey waypoints within the polygon bounding box', () => {
    const wps = generateGrid(SQUARE, DEFAULT_CAMERA, PARAMS)
    const lats = SQUARE.map((p) => p.lat)
    const lons = SQUARE.map((p) => p.lon)
    const minLat = Math.min(...lats) - 0.0005
    const maxLat = Math.max(...lats) + 0.0005
    const minLon = Math.min(...lons) - 0.0005
    const maxLon = Math.max(...lons) + 0.0005
    for (const wp of wps) {
      expect(wp.lat).toBeGreaterThanOrEqual(minLat)
      expect(wp.lat).toBeLessThanOrEqual(maxLat)
      expect(wp.lon).toBeGreaterThanOrEqual(minLon)
      expect(wp.lon).toBeLessThanOrEqual(maxLon)
    }
  })

  it('produces more lines when side overlap is higher (tighter spacing)', () => {
    const loose = generateGrid(SQUARE, DEFAULT_CAMERA, { ...PARAMS, sideOverlap: 0.5 })
    const tight = generateGrid(SQUARE, DEFAULT_CAMERA, { ...PARAMS, sideOverlap: 0.9 })
    expect(tight.length).toBeGreaterThan(loose.length)
  })
})

describe('generatePerimeter', () => {
  it('returns a closed loop (last survey point near first)', () => {
    const wps = generatePerimeter(SQUARE, DEFAULT_CAMERA, PARAMS)
    expect(wps.length).toBeGreaterThan(3)
  })
})

describe('generateCorridor', () => {
  it('returns waypoints for a drawn line', () => {
    const line: LatLon[] = [
      { lat: 18.5200, lon: 73.8550 },
      { lat: 18.5182, lon: 73.8569 },
    ]
    const wps = generateCorridor(line, DEFAULT_CAMERA, PARAMS)
    expect(wps.length).toBeGreaterThan(2)
  })
})

describe('computeStats', () => {
  it('computes positive area, distance, image count and flight time', () => {
    const wps = generateGrid(SQUARE, DEFAULT_CAMERA, PARAMS)
    const stats = computeStats(wps, SQUARE, DEFAULT_CAMERA, PARAMS)
    expect(stats.areaHa).toBeGreaterThan(3)
    expect(stats.areaHa).toBeLessThan(5)
    expect(stats.distanceM).toBeGreaterThan(0)
    expect(stats.imageCount).toBeGreaterThan(0)
    expect(stats.flightTimeSec).toBeGreaterThan(stats.distanceM / PARAMS.speedMs)
    expect(stats.gsdCm).toBeCloseTo((20 * 7.68) / (25 * 640) * 100, 1)
  })
})
