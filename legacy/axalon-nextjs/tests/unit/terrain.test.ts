import { afterEach, describe, expect, test, vi } from 'vitest'
import { applyTerrainOffsets, fetchElevations, MIN_SAFE_ALT_M } from '@/lib/terrain'
import type { Waypoint } from '@/lib/missionGeometry'

function wp(lat: number, lon: number, alt = 20): Waypoint {
  return { lat, lon, alt }
}

describe('applyTerrainOffsets', () => {
  test('keeps altitude constant over flat ground', () => {
    const wps = [wp(18.5, 73.8), wp(18.501, 73.8), wp(18.502, 73.8)]
    const out = applyTerrainOffsets(wps, [550, 550, 550])
    expect(out.map((w) => w.alt)).toEqual([20, 20, 20])
  })

  test('raises altitude over rising ground relative to first waypoint', () => {
    const wps = [wp(18.5, 73.8), wp(18.501, 73.8)]
    const out = applyTerrainOffsets(wps, [550, 562.4])
    expect(out[0].alt).toBe(20)
    expect(out[1].alt).toBeCloseTo(32.4, 1)
  })

  test('lowers altitude over falling ground but clamps to safe minimum', () => {
    const wps = [wp(18.5, 73.8), wp(18.501, 73.8)]
    const out = applyTerrainOffsets(wps, [550, 500])
    expect(out[1].alt).toBe(MIN_SAFE_ALT_M)
  })

  test('does not mutate the input waypoints', () => {
    const wps = [wp(18.5, 73.8), wp(18.501, 73.8)]
    applyTerrainOffsets(wps, [550, 560])
    expect(wps[1].alt).toBe(20)
  })

  test('falls back to original waypoints when elevation count mismatches', () => {
    const wps = [wp(18.5, 73.8), wp(18.501, 73.8)]
    expect(applyTerrainOffsets(wps, [550])).toEqual(wps)
  })

  test('preserves heading/gimbal/leg metadata', () => {
    const wps: Waypoint[] = [{ lat: 18.5, lon: 73.8, alt: 20, heading: 90, gimbalPitch: -45, leg: 1 }]
    const out = applyTerrainOffsets(wps, [550])
    expect(out[0]).toMatchObject({ heading: 90, gimbalPitch: -45, leg: 1 })
  })
})

describe('fetchElevations', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  test('returns elevations in order from the lookup API', async () => {
    const mock = vi.fn().mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          results: [
            { latitude: 18.5, longitude: 73.8, elevation: 550 },
            { latitude: 18.501, longitude: 73.8, elevation: 561 },
          ],
        }),
    })
    vi.stubGlobal('fetch', mock)

    const out = await fetchElevations([
      { lat: 18.5, lon: 73.8 },
      { lat: 18.501, lon: 73.8 },
    ])
    expect(out).toEqual([550, 561])
    expect(mock).toHaveBeenCalledTimes(1)
  })

  test('batches large requests', async () => {
    const points = Array.from({ length: 250 }, (_, i) => ({ lat: 18 + i * 1e-4, lon: 73.8 }))
    const mock = vi.fn().mockImplementation((_url: string, init: RequestInit) => {
      const body = JSON.parse(String(init.body)) as { locations: { latitude: number }[] }
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            results: body.locations.map((l) => ({ ...l, elevation: 500 })),
          }),
      })
    })
    vi.stubGlobal('fetch', mock)

    const out = await fetchElevations(points)
    expect(out).toHaveLength(250)
    expect(mock.mock.calls.length).toBeGreaterThan(1)
  })

  test('returns null when the API fails (graceful fallback)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')))
    expect(await fetchElevations([{ lat: 18.5, lon: 73.8 }])).toBeNull()
  })

  test('returns null on non-OK response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 502 }))
    expect(await fetchElevations([{ lat: 18.5, lon: 73.8 }])).toBeNull()
  })
})
